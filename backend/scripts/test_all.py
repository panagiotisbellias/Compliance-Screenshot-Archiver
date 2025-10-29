#!/usr/bin/env python3
"""
Comprehensive testing script for Compliance Screenshot Archiver.

This script combines all testing approaches from TESTING_GUIDE.md into one executable script:
- Unit tests with coverage
- Code quality validation (ruff, mypy)
- FastAPI server startup testing
- Integration tests
- Environment setup validation
- Test report generation

Usage:
    python scripts/test_all.py [options]

Examples:
    # Run all tests with default settings
    python scripts/test_all.py
    ./scripts/test

    # Quick mode for development
    python scripts/test_all.py --quick
    ./scripts/test quick

    # Run only unit tests
    python scripts/test_all.py --unit-only
    ./scripts/test unit

    # Run with custom coverage threshold
    python scripts/test_all.py --coverage-threshold 85

    # Skip code quality checks
    python scripts/test_all.py --skip-quality

    # Run tests with debug output
    python scripts/test_all.py --debug

    # Generate detailed report for CI
    python scripts/test_all.py --detailed-report
    ./scripts/test ci
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.main import app

# Add the app directory to the Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Test result container."""

    name: str
    success: bool
    duration: float
    output: str = ""
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestReport:
    """Comprehensive test report."""

    start_time: datetime
    end_time: datetime | None = None
    total_duration: float = 0.0
    results: list[TestResult] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def add_result(self, result: TestResult) -> None:
        """Add a test result."""
        self.results.append(result)
        logger.info(f"{'✅' if result.success else '❌'} {result.name} ({result.duration:.2f}s)")
        if result.error and not result.success:
            logger.error(f"  Error: {result.error}")

    def finalize(self) -> None:
        """Finalize the report."""
        self.end_time = datetime.now()
        self.total_duration = (self.end_time - self.start_time).total_seconds()

        # Calculate summary
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests

        self.summary = {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            "total_duration": self.total_duration,
        }

    def print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Total Duration: {self.total_duration:.2f}s")
        print(f"Total Tests: {self.summary['total_tests']}")
        print(f"Passed: {self.summary['passed']} ✅")
        print(f"Failed: {self.summary['failed']} ❌")
        print(f"Success Rate: {self.summary['success_rate']:.1f}%")
        print()

        if self.summary["failed"] > 0:
            print("FAILED TESTS:")
            print("-" * 40)
            for result in self.results:
                if not result.success:
                    print(f"❌ {result.name}")
                    if result.error:
                        print(f"   Error: {result.error}")
            print()

        overall_success = self.summary["failed"] == 0
        status_icon = "✅" if overall_success else "❌"
        status_text = "PASSED" if overall_success else "FAILED"
        print(f"{status_icon} OVERALL STATUS: {status_text}")
        print("=" * 80)

    def save_json_report(self, filepath: Path) -> None:
        """Save detailed JSON report."""
        report_data = {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_duration": self.total_duration,
            "environment": self.environment,
            "summary": self.summary,
            "results": [
                {
                    "name": r.name,
                    "success": r.success,
                    "duration": r.duration,
                    "output": r.output,
                    "error": r.error,
                    "details": r.details,
                }
                for r in self.results
            ],
        }

        with open(filepath, "w") as f:
            json.dump(report_data, f, indent=2)

        logger.info(f"Detailed report saved to: {filepath}")


class TestRunner:
    """Main test runner class."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.report = TestReport(start_time=datetime.now())
        self.setup_environment()

    def setup_environment(self) -> None:
        """Setup test environment and validate prerequisites."""
        logger.info("Setting up test environment...")

        # Set test environment variables
        os.environ["APP_ENV"] = "test"
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["S3_BUCKET_ARTIFACTS"] = "test-artifacts-bucket"
        os.environ["KMS_KEY_ARN"] = "arn:aws:kms:us-east-1:123456789012:key/test-key"
        os.environ["DDB_TABLE_SCHEDULES"] = "test-schedules"
        os.environ["DDB_TABLE_CAPTURES"] = "test-captures"

        # Mock AWS credentials
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        # Store environment info
        self.report.environment = {
            "python_version": sys.version,
            "platform": sys.platform,
            "cwd": str(Path.cwd()),
            "app_env": os.environ.get("APP_ENV", "unknown"),
            "aws_region": os.environ.get("AWS_REGION", "unknown"),
        }

    def run_command(
        self, cmd: list[str], name: str, cwd: Path | None = None, timeout: int = 300
    ) -> TestResult:
        """Run a command and return test result."""
        start_time = time.time()

        try:
            logger.info(f"Running: {name}")
            if self.args.debug:
                logger.debug(f"Command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=cwd or PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            duration = time.time() - start_time
            success = result.returncode == 0

            return TestResult(
                name=name,
                success=success,
                duration=duration,
                output=result.stdout,
                error=result.stderr if not success else "",
                details={"returncode": result.returncode, "command": " ".join(cmd)},
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                name=name,
                success=False,
                duration=duration,
                error=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(name=name, success=False, duration=duration, error=str(e))

    def validate_environment(self) -> TestResult:
        """Validate environment setup."""
        start_time = time.time()
        errors = []

        # Check Python version
        if sys.version_info < (3, 12):
            errors.append(f"Python 3.12+ required, got {sys.version}")

        # Check required files
        required_files = [
            PROJECT_ROOT / "pyproject.toml",
            PROJECT_ROOT / "app" / "main.py",
            PROJECT_ROOT / "tests" / "conftest.py",
        ]

        for file_path in required_files:
            if not file_path.exists():
                errors.append(f"Required file missing: {file_path}")

        # Check UV availability
        try:
            subprocess.run(["uv", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            errors.append("UV package manager not available")

        duration = time.time() - start_time
        success = len(errors) == 0

        return TestResult(
            name="Environment Validation",
            success=success,
            duration=duration,
            error="; ".join(errors) if errors else "",
            details={"checks": len(required_files) + 2, "errors": len(errors)},
        )

    def run_unit_tests(self) -> TestResult:
        """Run unit tests with coverage."""
        cmd = ["uv", "run", "pytest", "tests/"]

        # Add coverage options
        if self.args.coverage_threshold > 0:
            cmd.extend(
                [
                    "--cov=app",
                    "--cov-report=term-missing",
                    "--cov-report=html",
                    f"--cov-fail-under={self.args.coverage_threshold}",
                ]
            )

        # Add verbosity
        if self.args.debug:
            cmd.extend(["-v", "-s", "--log-cli-level=DEBUG"])
        elif self.args.verbose:
            cmd.append("-v")

        # Add test markers if specified
        if self.args.unit_only:
            cmd.extend(["-m", "not integration"])

        # Add quiet flag for cleaner output unless debug mode
        if not self.args.debug and not self.args.verbose:
            cmd.append("-q")

        return self.run_command(cmd, "Unit Tests with Coverage")

    def run_code_quality_checks(self) -> list[TestResult]:
        """Run code quality checks."""
        results = []

        if not self.args.skip_quality:
            # Ruff linting
            results.append(
                self.run_command(["uv", "run", "ruff", "check", "app/", "tests/"], "Ruff Linting")
            )

            # Ruff formatting check
            results.append(
                self.run_command(
                    ["uv", "run", "ruff", "format", "--check", "app/", "tests/"],
                    "Ruff Format Check",
                )
            )

            # MyPy type checking
            results.append(self.run_command(["uv", "run", "mypy", "app/"], "MyPy Type Checking"))

        return results

    def test_server_startup(self) -> TestResult:
        """Test FastAPI server startup."""
        start_time = time.time()

        try:
            # Check if app is properly configured
            if not hasattr(app, "routes") or len(app.routes) == 0:
                raise Exception("FastAPI app has no routes configured")

            # Test health endpoint availability
            health_route_found = False
            for route in app.routes:
                if hasattr(route, "path") and "/health" in route.path:
                    health_route_found = True
                    break

            if not health_route_found:
                raise Exception("Health endpoint not found in routes")

            duration = time.time() - start_time
            return TestResult(
                name="FastAPI Server Startup",
                success=True,
                duration=duration,
                details={"routes_count": len(app.routes)},
            )

        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="FastAPI Server Startup", success=False, duration=duration, error=str(e)
            )

    def run_integration_tests(self) -> TestResult:
        """Run integration tests."""
        cmd = ["uv", "run", "pytest", "tests/", "-m", "integration"]

        if self.args.debug:
            cmd.extend(["-v", "-s", "--log-cli-level=DEBUG"])
        elif self.args.verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")

        return self.run_command(cmd, "Integration Tests")

    def test_live_server(self) -> TestResult:
        """Test live server endpoints if available."""
        start_time = time.time()

        try:
            # Try to connect to local server
            base_url = "http://localhost:8000"
            timeout = 5

            with httpx.Client(timeout=timeout) as client:
                # Test health endpoint
                response = client.get(f"{base_url}/health")

                if response.status_code != 200:
                    raise Exception(f"Health check failed: {response.status_code}")

                health_data = response.json()
                if health_data.get("status") != "ok":
                    raise Exception(f"Health check returned unexpected status: {health_data}")

            duration = time.time() - start_time
            return TestResult(
                name="Live Server Test",
                success=True,
                duration=duration,
                details={"base_url": base_url, "endpoints_tested": 1},
            )

        except httpx.ConnectError:
            duration = time.time() - start_time
            return TestResult(
                name="Live Server Test",
                success=False,
                duration=duration,
                error="Server not running (this is expected if no server is started)",
            )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Live Server Test", success=False, duration=duration, error=str(e)
            )

    def run_all_tests(self) -> None:
        """Run all tests based on configuration."""
        logger.info("Starting comprehensive test suite...")
        logger.info(f"Debug mode: {self.args.debug}")
        logger.info(f"Coverage threshold: {self.args.coverage_threshold}%")
        if self.args.unit_only:
            logger.info("Running unit tests only")
        elif self.args.integration_only:
            logger.info("Running integration tests only")
        if self.args.skip_quality:
            logger.info("Skipping code quality checks")

        # 1. Environment validation
        self.report.add_result(self.validate_environment())

        # 2. Code quality checks
        for result in self.run_code_quality_checks():
            self.report.add_result(result)

        # 3. FastAPI server startup test
        self.report.add_result(self.test_server_startup())

        # 4. Unit tests
        if not self.args.integration_only:
            self.report.add_result(self.run_unit_tests())

        # 5. Integration tests (if not unit-only)
        if not self.args.unit_only:
            self.report.add_result(self.run_integration_tests())

        # 6. Live server test (optional)
        if self.args.test_live_server:
            self.report.add_result(self.test_live_server())

        # Finalize report
        self.report.finalize()

        # Print summary
        self.report.print_summary()

        # Save detailed report if requested
        if self.args.detailed_report:
            report_file = (
                PROJECT_ROOT / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            self.report.save_json_report(report_file)

        # Print coverage report location if HTML coverage was generated
        if self.args.coverage_threshold > 0 and not self.args.integration_only:
            coverage_html = PROJECT_ROOT / "htmlcov" / "index.html"
            if coverage_html.exists():
                logger.info(f"HTML coverage report available at: {coverage_html}")

        # Exit with appropriate code
        sys.exit(0 if self.report.summary["failed"] == 0 else 1)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Comprehensive testing script for Compliance Screenshot Archiver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Test selection options
    parser.add_argument(
        "--unit-only", action="store_true", help="Run only unit tests (skip integration tests)"
    )

    parser.add_argument(
        "--integration-only",
        action="store_true",
        help="Run only integration tests (skip unit tests)",
    )

    parser.add_argument(
        "--skip-quality", action="store_true", help="Skip code quality checks (ruff, mypy)"
    )

    # Coverage options
    parser.add_argument(
        "--coverage-threshold",
        type=int,
        default=90,
        help="Minimum coverage percentage required (default: 90)",
    )

    # Output options
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    parser.add_argument("--debug", action="store_true", help="Debug mode with detailed output")

    parser.add_argument(
        "--detailed-report", action="store_true", help="Generate detailed JSON report"
    )

    # Server testing
    parser.add_argument(
        "--test-live-server",
        action="store_true",
        help="Test against running server (requires server to be started)",
    )

    # Quick mode
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: skip integration tests and use lower coverage threshold "
        "(useful for development)",
    )

    args = parser.parse_args()

    # Handle quick mode
    if args.quick:
        args.unit_only = True
        if args.coverage_threshold == 90:  # If default threshold
            args.coverage_threshold = 60
        logger.info("Quick mode enabled: unit tests only with 60% coverage threshold")

    # Validate argument combinations
    if args.unit_only and args.integration_only:
        parser.error("Cannot specify both --unit-only and --integration-only")

    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    # Run tests
    runner = TestRunner(args)
    runner.run_all_tests()


if __name__ == "__main__":
    main()
