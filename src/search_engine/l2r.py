import math
import pandas as pd
import numpy as np
import lightgbm
from collections import defaultdict

class LambdaMART:
    def __init__(self, params=None) -> None:
        """
        Initializes a LambdaMART (LGBMRanker) model using the lightgbm library.

        Args:
            params (dict, optional): Parameters for the LGBMRanker model. Defaults to None.
        """
        default_params = {
            'objective': "lambdarank",
            'boosting_type': "gbdt",
            'n_estimators': 100,
            'importance_type': "gain",
            'metric': "ndcg",
            'num_leaves': 31,
            'learning_rate': 0.1,
            'max_depth': -1,
            "n_jobs": -1,
        }

        if params:
            default_params.update(params)

        # Initialize the LGBMRanker with the provided parameters
        self.model = lightgbm.LGBMRanker(**default_params)

    def fit(self, X_train, y_train, qgroups_train):
        """
        Trains the LGBMRanker model.

        Args:
            X_train (array-like): Training input samples.
            y_train (array-like): Target values.
            qgroups_train (array-like): Query group sizes for training data.

        Returns:
            self: Returns the instance itself.
        """
        self.model.fit(X_train, y_train, group=qgroups_train)
        return self

    def predict(self, featurized_docs):
        """
        Predicts the target values for the given test data.

        Args:
            featurized_docs (array-like): 
                A list of featurized documents where each document is a list of its features
                All documents should have the same length.

        Returns:
            array-like: The estimated ranking for each document (unsorted)
        """
        return self.model.predict(featurized_docs)

class L2RFeatureExtractor:
    def __init__(self, document_index, title_index,
                 document_preprocessor, stopwords,
                 docid_to_network_features=None) -> None:
        self.document_index = document_index
        self.title_index = title_index
        self.document_preprocessor = document_preprocessor
        self.stopwords = stopwords
        self.docid_to_network_features = docid_to_network_features or {}
        self.hierarchy_mapping = {}
        self.current_mapping = 0
        self.hierarchy_levels = ['level1', 'level2', 'level3', 'level4']
        self.sibling_counts = defaultdict(int)
        self.compute_sibling_counts()

    def process_term(self, term):
        token = term.lower()
        if token in self.stopwords:
            return ''
        return token
    
    def parse_hierarchy_url(self, url):
        """
        Parses the hierarchical URL into its constituent levels, excluding the first two components.

        Args:
            url (str): The hierarchical URL.

        Returns:
            list: A list of hierarchy levels (4 levels).
        """
        # Remove leading and trailing slashes and split by '/'
        path = url.strip('/').split('/')
        
        # Exclude the first two components: "ICD10CM" and "Codes"
        if len(path) <= 2:
            return []  # No hierarchy levels present
        hierarchy_levels = path[2:]
        
        return hierarchy_levels

    def get_article_length(self, docid: int) -> int:
        return self.document_index.document_metadata[docid]['length']

    def get_title_length(self, docid: int) -> int:
        return self.title_index.document_metadata[docid]['length']

    def get_tf(self, index, docid, word_counts, query_parts):
        tf = 0.0
        for term in query_parts:
            processed_term = self.process_term(term)
            if not processed_term:
                continue
            tf += math.log(word_counts.get(processed_term, 0) + 1)
        return tf

    def get_tf_idf(self, index, docid, word_counts, query_parts):
        tf_idf = 0.0
        N = index.get_statistics()['number_of_documents']
        for term in query_parts:
            processed_term = self.process_term(term)
            if not processed_term:
                continue
            tf = math.log(word_counts.get(processed_term, 0) + 1)
            df = index.get_term_metadata(processed_term)['doc_frequency']
            idf = math.log(N / (df + 1))
            tf_idf += tf * idf
        return tf_idf

    def get_BM25_score(self, docid, doc_word_counts, query_parts):
        bm25 = 0.0
        stats = self.document_index.get_statistics()
        N = stats['number_of_documents']
        avgdl = stats['mean_document_length']
        doc_length = self.document_index.document_metadata[docid]['length']
        k1 = 1.2
        b = 0.75
        for term in query_parts:
            processed_term = self.process_term(term)
            if not processed_term:
                continue
            df = self.document_index.get_term_metadata(processed_term)['doc_frequency']
            if df == 0:
                continue
            idf = math.log((N - df + 0.5) / (df + 0.5))
            f_td = doc_word_counts.get(processed_term, 0)
            tf = ((k1 + 1) * f_td) / (k1 * (1 - b + b * (doc_length / avgdl)) + f_td)
            bm25 += idf * tf
        return bm25

    def get_pivoted_normalization_score(self, docid, doc_word_counts, query_parts):
        pn = 0.0
        stats = self.document_index.get_statistics()
        avgdl = stats['mean_document_length']
        N = stats['number_of_documents']
        doc_length = self.document_index.document_metadata[docid]['length']

        for term in query_parts:
            processed_term = self.process_term(term)
            if not processed_term:
                continue
            df = self.document_index.get_term_metadata(processed_term)['doc_frequency']
            if df == 0:
                continue
            qf = 1
            f_td = doc_word_counts.get(processed_term, 0)
            if f_td <= 0:
                continue
            norm_tf = (1 + math.log(1 + math.log(f_td))) / (1 - 0.2 + 0.2 * (doc_length / avgdl))
            idf = math.log((N + 1) / df)
            pn += qf * idf * norm_tf
        return pn

    def get_pagerank_score(self, docid):
        """
        Gets the PageRank score for the given document.

        Args:
            docid: The id of the document

        Returns:
            The PageRank score
        """
        return self.docid_to_network_features.get(docid, {}).get('pagerank', 0.0)

    def get_hits_hub_score(self, docid):
        """
        Gets the HITS hub score for the given document.

        Args:
            docid: The id of the document

        Returns:
            The HITS hub score
        """
        return self.docid_to_network_features.get(docid, {}).get('hub_score', 0.0)

    def get_hits_authority_score(self, docid):
        """
        Gets the HITS authority score for the given document.

        Args:
            docid: The id of the document

        Returns:
            The HITS authority score
        """
        return self.docid_to_network_features.get(docid, {}).get('authority_score', 0.0)
    
    def get_hierarchy(self, docid):
        """
        Gets the hierarchy score for the given document.

        Args:
            docid: The id of the document

        Returns:
            The hierarchy score
        """
        return self.document_index.document_metadata[docid]['url']

    def get_hierarchy_encoded(self, docid):
        """
        Encodes the hierarchy URL into a single or multiple numerical features that respect the hierarchy.

        Args:
            docid: The id of the document

        Returns:
            list: A list of encoded hierarchy features.
        """
        url = self.get_hierarchy(docid)
        levels = self.parse_hierarchy_url(url)
        
        encoded_hierarchy = []
        for i, level in enumerate(levels):
            if i >= len(self.hierarchy_levels):
                break
            key = (self.hierarchy_levels[i], level)
            if key not in self.hierarchy_mapping:
                self.hierarchy_mapping[key] = self.current_mapping
                self.current_mapping += 1
            encoded_value = self.hierarchy_mapping[key]
            encoded_hierarchy.append(encoded_value)
        
        # If some hierarchy levels are missing, pad with -1 
        while len(encoded_hierarchy) < len(self.hierarchy_levels):
            encoded_hierarchy.append(-1)
        
        return encoded_hierarchy
    

    def compute_sibling_counts(self):
        """
        Computes the number of siblings for each hierarchy level.
        """
        for doc_meta in self.document_index.document_metadata.values():
            url = doc_meta['url']
            levels = self.parse_hierarchy_url(url)
            for i, level in enumerate(levels):
                if i >= len(self.hierarchy_levels):
                    break
                parent = '/'.join(levels[:i]) if i > 0 else 'root'
                key = (parent, i)
                self.sibling_counts[key] += 1

    def get_sibling_count(self, docid):
        url = self.get_hierarchy(docid)
        levels = self.parse_hierarchy_url(url)
        if not levels:
            return 0
        last_level = levels[-1]
        parent = '/'.join(levels[:-1]) if len(levels) > 1 else 'root'
        key = (parent, len(levels)-1)
        return self.sibling_counts.get(key, 0)
    
    def get_query_term_coverage(self, doc_word_counts, query_parts):
        """
        Calculates the Query Term Coverage feature.

        Args:
            doc_word_counts (dict): Word counts for the document's main text.
            query_parts (list): Tokenized query terms.

        Returns:
            float: Normalized coverage score between 0 and 1.
        """
        # Extract unique query terms
        unique_query_terms = set(query_parts)
        total_unique_query_terms = len(unique_query_terms)
        
        if total_unique_query_terms == 0:
            return 0.0  # Avoid division by zero
        
        # Extract unique document terms
        document_terms = set(doc_word_counts.keys())
        
        # Calculate coverage
        covered_terms = unique_query_terms.intersection(document_terms)
        coverage_count = len(covered_terms)
        
        # Normalize coverage
        normalized_coverage = coverage_count / total_unique_query_terms
        
        return normalized_coverage

    def get_jaccard_similarity(self, doc_word_counts, query_parts):
        """
        Calculates the Jaccard Similarity between the query and the document.

        Args:
            doc_word_counts (dict): Word counts for the document's main text.
            query_parts (list): Tokenized query terms.

        Returns:
            float: Jaccard Similarity score between 0 and 1.
        """
        # Convert lists of words to sets of unique terms
        query_terms = set(query_parts)
        document_terms = set(doc_word_counts.keys())

        # Calculate intersection and union
        intersection = query_terms.intersection(document_terms)
        union = query_terms.union(document_terms)

        # Handle division by zero
        if not union:
            return 0.0

        # Compute Jaccard Similarity
        jaccard_similarity = len(intersection) / len(union)

        return jaccard_similarity

    def generate_features(self, docid, doc_word_counts, title_word_counts, query_parts, query_text):
        """
        Generates a vector of features for a given document and query.

        Args:
            docid: The id of the document to generate features for
            doc_word_counts: The words in the document's main text mapped to their frequencies
            title_word_counts: The words in the document's title mapped to their frequencies
            query_parts : A list of tokenized query terms to generate features for

        Returns:
            A vector (list) of the features for this document
        """

        feature_vector = []

        # Document Length
        article_length = self.get_article_length(docid)
        feature_vector.append(article_length)

        # Title Length
        title_length = self.get_title_length(docid)
        feature_vector.append(title_length)

        # Query Length
        query_length = len(query_parts)
        feature_vector.append(query_length)

        # TF (document)
        tf_doc = self.get_tf(self.document_index, docid, doc_word_counts, query_parts)
        feature_vector.append(tf_doc)

        # TF-IDF (document)
        tf_idf_doc = self.get_tf_idf(self.document_index, docid, doc_word_counts, query_parts)
        feature_vector.append(tf_idf_doc)

        # TF (title)
        tf_title = self.get_tf(self.title_index, docid, title_word_counts, query_parts)
        feature_vector.append(tf_title)

        # TF-IDF (title)
        tf_idf_title = self.get_tf_idf(self.title_index, docid, title_word_counts, query_parts)
        feature_vector.append(tf_idf_title)

        # BM25
        bm25_score = self.get_BM25_score(docid, doc_word_counts, query_parts)
        feature_vector.append(bm25_score)

        # Pivoted normalization
        pivoted_norm_score = self.get_pivoted_normalization_score(docid, doc_word_counts, query_parts)
        feature_vector.append(pivoted_norm_score)

        # PageRank
        pagerank_score = self.get_pagerank_score(docid)
        feature_vector.append(pagerank_score)

        # HITS Hub Score
        hits_hub_score = self.get_hits_hub_score(docid)
        feature_vector.append(hits_hub_score)

        # HITS Authority Score
        hits_authority_score = self.get_hits_authority_score(docid)
        feature_vector.append(hits_authority_score)

        # Hierarchy Encoded Features
        hierarchy_encoded = self.get_hierarchy_encoded(docid)
        feature_vector.extend(hierarchy_encoded)

        # Sibling Count
        sibling_count = self.get_sibling_count(docid)
        feature_vector.append(sibling_count)

        # Query Term Coverage
        query_term_coverage = self.get_query_term_coverage(doc_word_counts, query_parts)
        feature_vector.append(query_term_coverage)

        # Jaccard Similarity
        jaccard_similarity = self.get_jaccard_similarity(doc_word_counts, query_parts)
        feature_vector.append(jaccard_similarity)

        return feature_vector

class L2RRanker:
    def __init__(self, document_index, title_index,
                 document_preprocessor, stopwords, ranker,
                 feature_extractor) -> None:
        """
        Initializes a L2RRanker model.

        Args:
            document_index: The inverted index for the contents of the document's main text body
            title_index: The inverted index for the contents of the document's title
            document_preprocessor: The DocumentPreprocessor to use for turning strings into tokens
            stopwords: The set of stopwords to use or None if no stopword filtering is to be done
            ranker: The base ranker to get initial candidate documents
            feature_extractor: The L2RFeatureExtractor object
        """
        self.document_index = document_index
        self.title_index = title_index
        self.document_preprocessor = document_preprocessor
        self.stopwords = stopwords
        self.ranker = ranker
        self.feature_extractor = feature_extractor
        self.model = LambdaMART()

    def prepare_training_data(self, query_to_document_relevance_scores):
        """
        Prepares the training data for the learning-to-rank algorithm.

        Args:
            query_to_document_relevance_scores (dict): A dictionary of queries mapped to a list of 
                documents and their relevance scores for that query
                The dictionary has the following structure:
                    query_1_text: [(docid_1, relevance_to_query_1), (docid_2, relevance_to_query_1), ...]

        Returns:
            tuple: A tuple containing the training data in the form of three lists: X, y, and qgroups
                X (list): A list of feature vectors for each query-document pair
                y (list): A list of relevance scores for each query-document pair
                qgroups (list): A list of the number of documents retrieved for each query
        """
        X = []
        y = []
        qgroups = []

        for query_text, docid_relevance_list in query_to_document_relevance_scores.items():
            # Tokenize
            query_tokens = self.document_preprocessor.tokenize(query_text)
            # Remove stopwords
            if self.stopwords:
                query_tokens = [token for token in query_tokens if token not in self.stopwords]

            num_docs = 0

            for docid, relevance_score in docid_relevance_list:
                # Convert docid to integer
                docid = docid

                # Check if docid exists
                if docid not in self.document_index.doc_term_freqs or docid not in self.title_index.doc_term_freqs:
                    continue

                # Word counts
                doc_word_counts = self.document_index.doc_term_freqs[docid]
                title_word_counts = self.title_index.doc_term_freqs[docid]

                # Generate features
                features = self.feature_extractor.generate_features(
                    docid, doc_word_counts, title_word_counts, query_tokens, query_text)

                # Add features and relevance score
                X.append(features)
                y.append(relevance_score)
                num_docs += 1

            if num_docs > 0:
                qgroups.append(num_docs)
        print(f"X:{X}")
        print("\n")
        print(f"y:{y}")
        print("\n")
        print(f"qgroups:{qgroups}")
        print("\n")

        return X, y, qgroups

    def train(self, query_to_document_relevance_scores):
        """
        Trains a LambdaMART pair-wise learning to rank model using the documents and relevance scores provided 
        in the training data.

        Args:
            query_to_document_relevance_scores (dict): A dictionary of queries mapped to a list of 
                documents and their relevance scores for that query
        """
        # Prepare training data
        X, y, qgroups = self.prepare_training_data(query_to_document_relevance_scores)
        if not X:
            raise ValueError("No training data prepared. Check if documents exist in the index.")
        
        # Convert to numpy arrays
        X = np.array(X)
        y = np.array(y)
        qgroups = np.array(qgroups)

        # Train the model
        self.model.fit(X, y, qgroups)

    def predict(self, X):
        """
        Predicts the ranks for featurized doc-query pairs using the trained model.

        Args:
            X (array-like): Input data to be predicted
                This is already featurized doc-query pairs.

        Returns:
            array-like: The predicted rank of each document

        Raises:
            ValueError: If the model has not been trained yet.
        """
        if self.model is None:
            raise ValueError("Model has not been trained yet.")
        return self.model.predict(X)

    def query(self, query, k=100):
        """
        Retrieves potentially-relevant documents, constructs feature vectors for each query-document pair,
        uses the L2R model to rank these documents, and returns the ranked documents.

        Args:
            query: A string representing the query to be used for ranking

        Returns:
            A list containing tuples of the ranked documents and their scores, sorted by score in descending order
                The list has the following structure: [(doc_id_1, score_1), (doc_id_2, score_2), ...]
        """
        query_tokens = self.document_preprocessor.tokenize(query)
        if self.stopwords:
            query_tokens = [token for token in query_tokens if token not in self.stopwords]
        if not query_tokens:
            return []

        # Get initial candidate documents using the base ranker
        initial_rankings = self.ranker.query(query, k=k)
        top_docids = [docid for docid, _ in initial_rankings]

        # Generate features for the top documents
        X = []
        docids = []
        for docid in top_docids:
            doc_word_counts = self.document_index.doc_term_freqs.get(docid, {})
            title_word_counts = self.title_index.doc_term_freqs.get(docid, {})
            features = self.feature_extractor.generate_features(
                docid, doc_word_counts, title_word_counts, query_tokens, query)
            X.append(features)
            docids.append(docid)
    

        # Predict scores using the model
        scores = self.predict(X)

        # Create a list and sort
        ranked_docs = list(zip(docids, scores))
        ranked_docs.sort(key=lambda x: x[1], reverse=True)

        return ranked_docs[:k]

    def save_model(self, filepath):
        self.model.model.booster_.save_model(filepath)

    def load_model(self, filepath):
        self.model.model = lightgbm.Booster(model_file=filepath)

class MiscFunctionsL2R():
    """
    miscellaneous functions
    """

    def load_network_features(self, file_path: str) -> dict[int, dict[str, float]]:
        """
        DESC: Load network features from a file

        PARAM: file_path: Path

        RETURN: A dictionary mapping document IDs to a dictionary of network features
        """
        df = pd.read_csv(file_path, index_col=0)
        return df.to_dict(orient='index')