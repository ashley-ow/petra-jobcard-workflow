from __future__ import annotations

from collections.abc import Iterable

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex, SearchableField, SimpleField
from azure.search.documents.indexes.models import SearchFieldDataType as DataType

from .config import Settings, settings, reveal
from .models import ReferenceChunk, SearchEvidence

_REQUIRED_FIELDS = {
    "id",
    "document_id",
    "source_file",
    "page_number",
    "chunk_number",
    "content",
}


class AzureSearchReferenceStore:
    """Direct client-side ingestion works with Azure AI Search Serverless and Dedicated tiers."""

    def __init__(self, settings: Settings) -> None:
        credential = (
            AzureKeyCredential(reveal(settings.azure_search_api_key))
            if settings.azure_search_api_key is not None
            else DefaultAzureCredential()
        )
        self.index_name = "job-card-reference" #settings.azure_search_index_name
        self.index_client = SearchIndexClient("https://gptkb-q6f7jlnpp6tnk.search.windows.net", credential) #settings.azure_search_endpoint, credential)
        self.search_client = SearchClient("https://gptkb-q6f7jlnpp6tnk.search.windows.net", self.index_name, credential) #settings.azure_search_endpoint, self.index_name, credential)

    def create_search_client():
        #endpoint = settings.azure_search_endpoint
        endpoint = "https://gptkb-q6f7jlnpp6tnk.search.windows.net"

        print("SEARCH CLIENT USING:")
        print(endpoint)

        return SearchClient(
            endpoint=endpoint,
            index_name="job-card-reference", #settings.azure_search_index_name,
            credential=AzureKeyCredential("JIGLVyzZOsi7qMAayXJgIGd6wohbuOaLbt1x5VXwmtAzSeDJWbI3"), #settings.azure_search_api_key
            #),
        )

    def create_index_client():

        endpoint = settings.azure_search_endpoint

        print("INDEX CLIENT USING:")
        print(endpoint)

        return SearchIndexClient(
            endpoint="https://gptkb-q6f7jlnpp6tnk.search.windows.net", #endpoint,
            credential=AzureKeyCredential("JIGLVyzZOsi7qMAayXJgIGd6wohbuOaLbt1x5VXwmtAzSeDJWbI3"),
            #    settings.azure_search_api_key
            #),
        )

    def ensure_index(self) -> None:
        try:
            existing = self.index_client.get_index(self.index_name)
        except ResourceNotFoundError:
            self.index_client.create_index(self._index_definition())
            return
        actual = {field.name for field in existing.fields}
        missing = _REQUIRED_FIELDS - actual
        if missing:
            raise RuntimeError(
                f"Existing index '{self.index_name}' is missing required fields: {sorted(missing)}. "
                "Use a new index name or update the schema."
            )

    def index_chunks(self, chunks: list[ReferenceChunk]) -> None:
        for batch in batched(chunks, 100):
            documents = [
                {
                    "id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "source_file": chunk.source_file,
                    "page_number": chunk.page_number,
                    "chunk_number": chunk.chunk_number,
                    "content": chunk.content,
                }
                for chunk in batch
            ]
            results = self.search_client.merge_or_upload_documents(documents=documents)
            failures = [result for result in results if not result.succeeded]
            if failures:
                details = "; ".join(f"{item.key}: {item.error_message}" for item in failures[:5])
                raise RuntimeError(f"Azure AI Search indexing failed: {details}")

    def search(self, project_description: str, document_id: str, top: int) -> list[SearchEvidence]:
        escaped = document_id.replace("'", "''")
        results = self.search_client.search(
            search_text=project_description,
            filter=f"document_id eq '{escaped}'",
            top=top,
            select=["id", "document_id", "source_file", "page_number", "chunk_number", "content"],
        )
        evidence = [
            SearchEvidence(
                chunk_id=item["id"],
                document_id=item["document_id"],
                source_file=item["source_file"],
                page_number=item["page_number"],
                chunk_number=item["chunk_number"],
                content=item["content"],
                score=item.get("@search.score"),
            )
            for item in results
        ]
        if not evidence:
            raise ValueError("Azure AI Search returned no matching reference text for this PDF.")
        return evidence

    def _index_definition(self) -> SearchIndex:
        return SearchIndex(
            name=self.index_name,
            fields=[
                SimpleField(name="id", type=DataType.String, key=True, filterable=True),
                SimpleField(name="document_id", type=DataType.String, filterable=True),
                SimpleField(name="source_file", type=DataType.String, filterable=True),
                SimpleField(name="page_number", type=DataType.Int32, filterable=True, sortable=True),
                SimpleField(name="chunk_number", type=DataType.Int32, filterable=True, sortable=True),
                SearchableField(name="content", type=DataType.String, analyzer_name="en.microsoft"),
            ],
        )


def batched(items: list[ReferenceChunk], size: int) -> Iterable[list[ReferenceChunk]]:
    for offset in range(0, len(items), size):
        yield items[offset : offset + size]
