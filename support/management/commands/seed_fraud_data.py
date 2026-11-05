from django.core.management.base import BaseCommand, CommandError

from support.fraud_test_data import (
    DEFAULT_PASSWORD,
    DemoDataError,
    remove_fraud_test_data,
    seed_fraud_test_data,
)


class Command(BaseCommand):
    help = (
        "Create demo customers with low, medium and high risk patterns for "
        "testing the Risk Agent (local development only)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Password for the demo customers (default: {DEFAULT_PASSWORD})",
        )
        parser.add_argument(
            "--remove",
            action="store_true",
            help="Delete the demo customers instead of creating them",
        )

    def handle(self, *args, **options):
        try:
            if options["remove"]:
                count = remove_fraud_test_data()
                self.stdout.write(self.style.SUCCESS(f"Removed {count} demo customer(s)."))
                return

            summary = seed_fraud_test_data(password=options["password"])
        except DemoDataError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS("Demo customers ready:"))
        for row in summary:
            self.stdout.write(
                f"  {row['username']:<6} expected risk {row['expected_risk']:<6} "
                f"chat about order #{row['live_case_order_id']}: {row['live_case']}"
            )
        self.stdout.write(f"Password for all demo customers: {options['password']}")
