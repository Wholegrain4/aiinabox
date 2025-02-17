from collections import Counter
from indexing import InvertedIndex
import math


class Ranker:
    """
    The Ranker class is responsible for generating a list of documents for a given query
    ordered by their scores.
    """
    def __init__(self, index, document_preprocessor, stopwords, scorer):
        """
        Initialize the Ranker.

        Args:
            index: An instance of InvertedIndex.
            document_preprocessor: An instance of your tokenizer/preprocessor.
            stopwords: A set of stopwords to filter out.
            scorer: An instance of a RelevanceScorer subclass.
        """
        self.index = index
        self.tokenize = document_preprocessor.tokenize
        self.scorer = scorer
        self.stopwords = stopwords

    def query(self, query_text, k):
        """
        Searches the collection for relevant documents to the query and
        returns the top k documents ordered by their relevance (most relevant first).

        Args:
            query_text: The query string.
            k: The number of top documents to return.

        Returns:
            A list of tuples containing (doc_id, score), sorted by score in descending order.
        """
        # Validate the parameter k
        if not isinstance(k, int) or k <= 0:
            raise ValueError("Parameter k must be a positive integer.")

        # Tokenize the query
        query_tokens = self.tokenize(query_text)
        if self.stopwords:
            query_tokens = [token for token in query_tokens if token not in self.stopwords]
        query_word_counts = Counter(query_tokens)

        # Get list of documents containing the query terms
        candidate_docs = set()
        for term in query_word_counts.keys():
            postings = self.index.get_postings(term)
            for posting in postings:
                candidate_docs.add(posting['doc_id'])

        # Score each candidate document
        scores = []
        for doc_id in candidate_docs:
            doc_word_counts = self.index.doc_term_freqs.get(doc_id, {})
            if not doc_word_counts:
                continue

            score = self.scorer.score(doc_id, doc_word_counts, query_word_counts)
            scores.append((doc_id, score))

        if not scores:
            return []

        # Sort the scores in descending order and slice the top k
        sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)
        top_k_scores = sorted_scores[:k]

        return top_k_scores


class RelevanceScorer:
    """
    Base class for all relevance scoring algorithms.
    """
    def __init__(self, index, parameters={}):
        """
        Initialize the RelevanceScorer.

        Args:
            index: An instance of InvertedIndex.
            parameters: A dictionary of parameters for the scorer.
        """
        self.index = index
        self.parameters = parameters

    def score(self, doc_id, doc_word_counts, query_word_counts):
        """
        Compute the relevance score of a document for a given query.

        Args:
            doc_id: The document ID.
            doc_word_counts: A Counter of term frequencies in the document.
            query_word_counts: A Counter of term frequencies in the query.

        Returns:
            A relevance score (float).
        """
        raise NotImplementedError("Subclasses should implement this method")


class WordCountCosineSimilarity(RelevanceScorer):
    """
    Implements unnormalized cosine similarity.
    """
    def __init__(self, index, parameters={}):
        super().__init__(index, parameters)

    def score(self, doc_id, doc_word_counts, query_word_counts):
        # Compute the dot product between the query and document term frequencies
        dot_product = 0
        for term, query_tf in query_word_counts.items():
            doc_tf = doc_word_counts.get(term, 0)
            dot_product += query_tf * doc_tf

        # Compute the magnitude of the document vector
        doc_magnitude = math.sqrt(sum(tf ** 2 for tf in doc_word_counts.values()))
        # Compute the magnitude of the query vector
        query_magnitude = math.sqrt(sum(tf ** 2 for tf in query_word_counts.values()))

        if doc_magnitude == 0 or query_magnitude == 0:
            return 0.0

        # Compute cosine similarity
        cosine_similarity = dot_product / (doc_magnitude * query_magnitude)
        return cosine_similarity


class TF_IDF(RelevanceScorer):
    """
    Implements the TF-IDF ranking function for relevance scoring.
    """
    def __init__(self, index, parameters={}):
        super().__init__(index, parameters)
        self.N = index.total_documents

    def score(self, doc_id, doc_word_counts, query_word_counts):
        score = 0.0
        for term in query_word_counts:
            tf_td = doc_word_counts.get(term, 0)
            if tf_td == 0:
                continue

            term_metadata = self.index.get_term_metadata(term)
            df_t = term_metadata['doc_frequency']
            if df_t == 0:
                continue

            idf = math.log((self.N + 1) / (df_t + 1))
            tf = 1 + math.log(tf_td)
            score += tf * idf
        return score


class BM25(RelevanceScorer):
    """
    Implements the BM25 ranking function for relevance scoring.
    """
    def __init__(self, index, parameters={'k1': 1.5, 'b': 0.75}):
        super().__init__(index, parameters)
        self.k1 = parameters.get('k1', 1.5)
        self.b = parameters.get('b', 0.75)
        self.N = index.total_documents
        stats = self.index.get_statistics()
        self.avgdl = stats['mean_document_length']

    def score(self, doc_id, doc_word_counts, query_word_counts):
        score = 0.0
        doc_length = self.index.document_lengths.get(doc_id, 0)
        for term in query_word_counts:
            term_metadata = self.index.get_term_metadata(term)
            df_t = term_metadata['doc_frequency']
            if df_t == 0:
                continue

            idf = math.log((self.N - df_t + 0.5) / (df_t + 0.5) + 1)

            tf_td = doc_word_counts.get(term, 0)
            if tf_td == 0:
                continue

            numerator = tf_td * (self.k1 + 1)
            denominator = tf_td + self.k1 * (1 - self.b + self.b * (doc_length / self.avgdl))
            tf_weight = numerator / denominator

            score += idf * tf_weight
        return score
    


class DirichletLM(RelevanceScorer):
    """
    Implements the Dirichlet Language Model for relevance scoring.
    """
    def __init__(self, index, parameters={'mu': 2000}):
        super().__init__(index, parameters)
        self.mu = parameters.get('mu', 2000)
        # Precompute collection statistics
        stats = self.index.get_statistics()
        self.collection_length = stats['total_token_count']
        # Compute collection term frequencies
        self.collection_term_freqs = {}
        for term, postings in self.index.index.items():
            collection_tf = sum(posting['tf'] for posting in postings)
            self.collection_term_freqs[term] = collection_tf

    def score(self, doc_id, doc_word_counts, query_word_counts):
        doc_length = self.index.document_lengths.get(doc_id, 0)
        mu = self.mu
        score = 0.0

        for term, query_tf in query_word_counts.items():
            doc_tf = doc_word_counts.get(term, 0)
            collection_tf = self.collection_term_freqs.get(term, 0)

            if collection_tf == 0:
                continue

            term_probability = (doc_tf + mu * (collection_tf / self.collection_length)) / (doc_length + mu)
            if term_probability > 0:
                score += query_tf * math.log(term_probability)

        return score



class PivotedNormalization(RelevanceScorer):
    """
    Implements Pivoted Normalization for relevance scoring.
    """
    def __init__(self, index, parameters={'b': 0.2}):
        super().__init__(index, parameters)
        self.b = parameters.get('b', 0.2)
        stats = self.index.get_statistics()
        self.avgdl = stats['mean_document_length']
        self.N = self.index.total_documents

    def score(self, doc_id, doc_word_counts, query_word_counts):
        doc_length = self.index.document_lengths.get(doc_id, 0)
        score = 0.0
        b = self.b
        avgdl = self.avgdl
        N = self.N

        for term, qf in query_word_counts.items():
            term_metadata = self.index.get_term_metadata(term)
            df_t = term_metadata['doc_frequency']
            if df_t == 0:
                continue

            idf = math.log((N + 1) / df_t)
            f_td = doc_word_counts.get(term, 0)
            if f_td == 0:
                continue

            # Compute normalized term frequency
            tf = (1 + math.log(1 + math.log(f_td))) / (1 - b + b * (doc_length / avgdl))
            score += qf * idf * tf

        return score
