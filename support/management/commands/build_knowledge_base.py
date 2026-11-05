from django.conf import settings
from django.core.management.base import BaseCommand

from support.knowledge_base import (
    DOCUMENTS_DIR,
    build_knowledge_base,
    search_knowledge_base,
)


class Command(BaseCommand):
    help = (
        "Load the company documents in support/documents/ into the ChromaDB "
        "knowledge base. Safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--query",
            help="After building, search the knowledge base and print the best matches",
        )

    def handle(self, *args, **options):
        summary = build_knowledge_base()
        self.stdout.write(self.style.SUCCESS(
            f"Knowledge base ready: {summary['documents']} document(s), "
            f"{summary['chunks']} chunk(s), {summary['removed']} stale chunk(s) removed."
        ))
        self.stdout.write(f"Documents: {DOCUMENTS_DIR}")
        self.stdout.write(f"Database:  {settings.CHROMA_PATH}")

        if options["query"]:
            self.stdout.write(f"\nTop matches for: {options['query']}")
            found = search_knowledge_base(options["query"])
            for result in found["results"]:
                preview = " ".join(result["text"].split())[:160]
                self.stdout.write(
                    f"  [{result['distance']}] {result['source']}: {preview}..."
                )
            if not found["results"]:
                self.stdout.write(f"  {found.get('note', 'No matches.')}")
