# indexing.py

from enum import Enum
from collections import Counter, defaultdict
import json
import os
import string
from document_preprocessor import Tokenizer
import chardet


class IndexType(Enum):
    """
    Index Type
    """
    BASIC = 'BasicInvertedIndex'


class InvertedIndex:
    """
    Implement the inverted index.
    """
    def __init__(self) -> None:
        """
        Initialize the inverted index.
        """
        # Change defaultdict from set to list to store postings with term frequencies
        self.index = defaultdict(list)  # Each term maps to a list of postings
        self.document_lengths = {}
        self.total_documents = 0
        self.doc_term_freqs = {}
        self.document_metadata = {}

    def add_document(self, doc_id: str, tokens: list[str], metadata: dict) -> None:
        """
        Add a document to the index with term frequencies.
        """
        if doc_id in self.document_lengths:
            print(f"Document with doc_id {doc_id} is already indexed.")
            return

        # Calculate term frequencies in the document
        term_freqs = Counter(tokens)
        self.doc_term_freqs[doc_id] = term_freqs  # Store term frequencies for the document

        # Update the inverted index with term frequencies
        for term, freq in term_freqs.items():
            self.index[term].append({'doc_id': doc_id, 'tf': freq})

        # Store document length
        self.document_lengths[doc_id] = len(tokens)
        self.total_documents += 1

        # Combine length with metadata
        metadata_with_length = metadata.copy()
        metadata_with_length['length'] = len(tokens)
        self.document_metadata[doc_id] = metadata_with_length

    def get_postings(self, term: str) -> list[dict]:
        """
        Get the postings list for a term.
        Each posting is a dictionary with keys 'doc_id' and 'tf'.
        """
        return self.index.get(term, [])

    def get_statistics(self):
        """
        Compute and return collection statistics.
        """
        total_token_count = sum(self.document_lengths.values())
        mean_document_length = total_token_count / self.total_documents if self.total_documents > 0 else 0
        return {
            'total_token_count': total_token_count,
            'mean_document_length': mean_document_length,
            'number_of_documents': self.total_documents,
        }

    def get_term_metadata(self, term: str):
        """
        Get metadata for a term, such as document frequency.
        """
        postings = self.get_postings(term)
        doc_frequency = len(postings)
        return {'doc_frequency': doc_frequency}

    def save(self, index_directory: str) -> None:
        """
        Save the index to disk.
        """
        os.makedirs(index_directory, exist_ok=True)

        # Save index
        with open(os.path.join(index_directory, 'index.json'), 'w', encoding='utf-8') as f:
            json.dump({term: postings for term, postings in self.index.items()}, f)

        # Save document lengths
        with open(os.path.join(index_directory, 'doc_lengths.json'), 'w', encoding='utf-8') as f:
            json.dump(self.document_lengths, f)

        # Save doc_term_freqs
        with open(os.path.join(index_directory, 'doc_term_freqs.json'), 'w', encoding='utf-8') as f:
            # Convert Counter objects to regular dicts for JSON serialization
            doc_term_freqs_as_dict = {doc_id: dict(freqs) for doc_id, freqs in self.doc_term_freqs.items()}
            json.dump(doc_term_freqs_as_dict, f)

        # Save document metadata
        with open(os.path.join(index_directory, 'document_metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(self.document_metadata, f)

    def load(self, index_directory: str) -> None:
        """
        Load the index from disk.
        """
        # Load index
        with open(os.path.join(index_directory, 'index.json'), 'r', encoding='utf-8') as f:
            index_data = json.load(f)
            self.index = defaultdict(list, {term: postings for term, postings in index_data.items()})

        # Load document lengths
        with open(os.path.join(index_directory, 'doc_lengths.json'), 'r', encoding='utf-8') as f:
            self.document_lengths = json.load(f)

        # Load doc_term_freqs
        with open(os.path.join(index_directory, 'doc_term_freqs.json'), 'r', encoding='utf-8') as f:
            doc_term_freqs_data = json.load(f)
            self.doc_term_freqs = {doc_id: Counter(freqs) for doc_id, freqs in doc_term_freqs_data.items()}

        # Load document metadata
        with open(os.path.join(index_directory, 'document_metadata.json'), 'r', encoding='utf-8') as f:
            self.document_metadata = json.load(f)

        self.total_documents = len(self.document_lengths)


class Indexer:
    @staticmethod
    def create_index(index_type: IndexType, dataset_path: str,
                    tokenizer: Tokenizer, text_keys: list[str] = ["text"],
                    id_key: str = "id", max_docs: int = -1) -> InvertedIndex:
        if index_type != IndexType.BASIC:
            raise ValueError("Unsupported index type.")

        index = InvertedIndex()

        # Detect encoding
        with open(dataset_path, 'rb') as ef:
            raw_data = ef.read(100000)
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            confidence = result['confidence']
            print(f"Detected encoding: {encoding} with confidence {confidence}")

        # Read and index documents
        with open(dataset_path, 'r', encoding=encoding, errors='replace') as f:
            for line_num, line in enumerate(f):
                if 0 < max_docs <= line_num:
                    break

                try:
                    doc = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON on line {line_num}: {e}")
                    continue

                # Combine text from specified keys
                text_parts = [str(doc.get(key, "")) for key in text_keys]
                text = ' '.join(text_parts)

                doc_id = doc.get(id_key)

                # Collect metadata
                doc_metadata = {
                    'title': doc.get('title', 'No Title'),
                    'text': text,
                    'url': doc.get('link', '#')
                }

                if doc_id is None:
                    print(f"Document missing '{id_key}' on line {line_num}. Skipping.")
                    continue

                tokens = tokenizer.tokenize(text)

                if line_num % 1000 == 0:
                    print(f"Processing document {line_num}...")

                index.add_document(doc_id, tokens, metadata=doc_metadata)

        return index
    
    @classmethod
    def load_index(cls, index_directory: str) -> InvertedIndex:
        """
        Load an existing index from the specified directory.
        """
        index = InvertedIndex()
        index.load(index_directory)
        return index
