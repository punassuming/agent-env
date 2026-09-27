"""Android Gradle bootstrap scenario that runs without an Android SDK.

Run with: python tests/scenarios/test_android_gradle.py -v
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))
from agent_env.bootstrap import discover, install


@unittest.skipIf(os.name == "nt", "synthetic Gradle wrapper is a POSIX shell script")
class AndroidGradleScenario(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "settings.gradle.kts").write_text(
            'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
            'dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\n'
            'rootProject.name = "sample"\ninclude(":app", ":core")\n'
        )
        (self.repo / "build.gradle.kts").write_text("plugins { id(\"com.android.application\") version \"8.7.3\" apply false }\n")
        app = self.repo / "app"
        app.mkdir()
        (app / "build.gradle.kts").write_text(
            'plugins { id("com.android.application") }\n'
            'android { namespace = "example.app"; compileSdk = 35; defaultConfig { applicationId = "example.app"; minSdk = 24 }\n'
            ' flavorDimensions += "tier"; productFlavors { create("demo") { dimension = "tier" }; create("full") { dimension = "tier" } } }\n'
        )
        (self.repo / "core").mkdir()
        (self.repo / "core" / "build.gradle.kts").write_text("plugins { id(\"java-library\") }\n")
        # Wrapper records tasks, and emulates Gradle's success/failure without a JDK/SDK.
        wrapper = self.repo / "gradlew"
        wrapper.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$GRADLE_LOG\"\n\n"
                           "case \" $* \" in *\" $GRADLE_FAIL \"*) exit 17;; esac\nexit 0\n")
        wrapper.chmod(0o755)
        (self.repo / "gradle").mkdir()
        (self.repo / "gradle" / "wrapper").mkdir()
        (self.repo / "gradle" / "wrapper" / "gradle-wrapper.properties").write_text(
            "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.9-bin.zip\n")

    def test_assess_install_and_execute_checks(self):
        candidate = discover(self.repo)
        self.assertEqual(set(candidate), {"root"})
        component = candidate["root"]
        self.assertIn("android", component["tools"])
        self.assertIn("gradle", component["tools"])
        # The conservative proposal intentionally asks for agent review on Android variants.
        self.assertIn("test", component["unconfigured"])
        self.assertIn("./gradlew", [s["argv"][0] for s in component["commands"]["validate"]])

        install(self.repo, candidate)
        # Pin representative flavor/variant tasks after reviewing the candidate.
        registry_path = self.repo / ".agents" / "commands.json"
        registry = json.loads(registry_path.read_text())
        commands = registry["components"]["root"]["commands"]
        commands["test"] = [{"argv": ["./gradlew", ":app:testDemoDebugUnitTest"]}]
        commands["build"] = [{"argv": ["./gradlew", ":app:assembleDemoDebug"]}]
        commands["validate"] = [{"argv": ["./gradlew", ":app:testDemoDebugUnitTest", ":app:assembleDemoDebug"]}]
        registry_path.write_text(json.dumps(registry, indent=2) + "\n")

        runner = self.repo / ".agents" / "bin" / "runtime.py"
        log = self.repo / "gradle.log"
        env = dict(os.environ, GRADLE_LOG=str(log), GRADLE_FAIL="")
        for command in ("test", "build", "validate"):
            result = subprocess.run([sys.executable, str(runner), command, "--all"], cwd=self.repo,
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text().splitlines(), [
            ":app:testDemoDebugUnitTest", ":app:assembleDemoDebug",
            ":app:testDemoDebugUnitTest :app:assembleDemoDebug"])

        failed = subprocess.run([sys.executable, str(runner), "validate", "--all"], cwd=self.repo,
                                env=dict(env, GRADLE_FAIL=":app:assembleDemoDebug"),
                                capture_output=True, text=True)
        self.assertEqual(failed.returncode, 17, failed.stderr)
        self.assertIn("FAILED root:validate", failed.stderr)


if __name__ == "__main__":
    unittest.main()
