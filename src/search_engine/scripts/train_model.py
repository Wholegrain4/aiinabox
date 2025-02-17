import os
import csv
from document_preprocessor import RegexTokenizer
from indexing import Indexer
from ranker import Ranker, BM25
from l2r import L2RFeatureExtractor, L2RRanker, MiscFunctionsL2R

# Load stop words
with open('stopwords.txt', 'r', encoding='utf-8') as f:
    stop_words = set(f.read().splitlines())

# Initialize the tokenizer
tokenizer = RegexTokenizer(stopwords=stop_words)

# Paths to the index directories
index_directory = 'index_directory'
title_index_directory = 'title_index_directory'

# Load indexes
print("Loading main index...")
index = Indexer.load_index(index_directory)
print("Main index loaded.")

print("Loading title index...")
title_index = Indexer.load_index(title_index_directory)
print("Title index loaded.")

# Initialize the scorer and ranker
bm25_scorer = BM25(index)
base_ranker = Ranker(
    index=index,
    document_preprocessor=tokenizer,
    stopwords=stop_words,
    scorer=bm25_scorer
)

# Initialize the feature extractor and L2R ranker
feature_extractor = L2RFeatureExtractor(
    document_index=index,
    title_index=title_index,
    document_preprocessor=tokenizer,
    stopwords=stop_words,
    docid_to_network_features=MiscFunctionsL2R().load_network_features("network_statistics.csv")
)

l2r_ranker = L2RRanker(
    document_index=index,
    title_index=title_index,
    document_preprocessor=tokenizer,
    stopwords=stop_words,
    ranker=base_ranker,
    feature_extractor=feature_extractor
)

# Prepare your training data
training_data_path = 'train_data_edited.csv'

# Load the training data
query_to_document_relevance_scores = {}
with open(training_data_path, 'r', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        query = row['Query'].strip()
        docid = row['docid'].strip()
        relevance = int(row['Rel Score'])

        # Add the data to the dictionary
        if query not in query_to_document_relevance_scores:
            query_to_document_relevance_scores[query] = []
        query_to_document_relevance_scores[query].append((docid, relevance))

# Train the model
print("Training the L2R model...")
l2r_ranker.train(query_to_document_relevance_scores)
print("Model trained successfully.")

# Save the trained model
l2r_ranker.save_model('l2r_model.txt')
print("Model saved to l2r_model.txt")
