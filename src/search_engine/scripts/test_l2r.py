import os
import pandas as pd
import numpy as np
import csv
from document_preprocessor import RegexTokenizer
from indexing import Indexer, IndexType
from ranker import Ranker, BM25, TF_IDF, WordCountCosineSimilarity, DirichletLM, PivotedNormalization
from l2r import L2RFeatureExtractor, L2RRanker, MiscFunctionsL2R
from relevance import map_score, ndcg_score, run_relevance_tests

# Load stop words from file
with open('stopwords.txt', 'r', encoding='utf-8') as f:
    stop_words = f.read().splitlines()
stop_words = set(stop_words)

# Initialize the tokenizer
tokenizer = RegexTokenizer(stopwords=stop_words)

# Paths to the index directories
index_directory = 'index_directory'
title_index_directory = 'title_index_directory'

# Path to the dataset
dataset_path = 'output.jsonl'

# Load or create the main index
if os.path.exists(index_directory):
    print("Loading existing main index...")
    index = Indexer.load_index(index_directory)
    print("Main index loaded successfully.")
else:
    print("Main index not found. Creating a new main index...")
    index = Indexer.create_index(
        index_type=IndexType.BASIC,
        dataset_path=dataset_path,
        tokenizer=tokenizer,
        text_keys=['text'],
        id_key='docid'
    )
    # Save the newly created index
    index.save(index_directory)
    print("New main index created and saved.")

# Load or create the title index
if os.path.exists(title_index_directory):
    print("Loading existing title index...")
    title_index = Indexer.load_index(title_index_directory)
    print("Title index loaded successfully.")
else:
    print("Title index not found. Creating a new title index...")
    title_index = Indexer.create_index(
        index_type=IndexType.BASIC,
        dataset_path=dataset_path,
        tokenizer=tokenizer,
        text_keys=['title'],  # Indexing the 'title' field
        id_key='docid'
    )
    # Save the newly created title index
    title_index.save(title_index_directory)
    print("New title index created and saved.")

# Initialize multiple scorers using the main index
scorers = {
    'BM25': BM25(index),
    'TF_IDF': TF_IDF(index),
    'CosineSimilarity': WordCountCosineSimilarity(index),
    'DirichletLM': DirichletLM(index),
    'PivotedNormalization': PivotedNormalization(index)
}

# Initialize rankers for each scorer
rankers = {}
for name, scorer in scorers.items():
    rankers[name] = Ranker(
        index=index,
        document_preprocessor=tokenizer,
        stopwords=stop_words,
        scorer=scorer
    )

# Path to your training data CSV file
training_data_path = 'train_data_edited.csv'

# Initialize an empty dictionary to hold the training data
query_to_document_relevance_scores = {}

# Read the training data from the CSV file
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


# Initialize the Feature Extractor and L2RRanker
# Initialize the feature extractor with both indexes
feature_extractor = L2RFeatureExtractor(
    document_index=index,
    title_index=title_index,
    document_preprocessor=tokenizer,
    stopwords=stop_words,
    docid_to_network_features=MiscFunctionsL2R().load_network_features("network_statistics.csv")
)

# Initialize the L2RRanker with both indexes
l2r_ranker = L2RRanker(
    document_index=index,
    title_index=title_index,
    document_preprocessor=tokenizer,
    stopwords=stop_words,
    ranker=rankers['BM25'],
    feature_extractor=feature_extractor
)


# Train the Model
print("Training the L2R model...")
l2r_ranker.train(query_to_document_relevance_scores)
print("Model trained successfully.")

# After training
feature_importances = l2r_ranker.model.model.feature_importances_
feature_names = ['article_length', 'title_length', 'query_length', 
                 'tf_doc', 'tf_idf_doc', 'tf_title', 'tf_idf_title', 
                 'bm25', 'pivoted_norm', 'pagerank', 'hits_hub', 
                 'hits_authority', "level1", "level2", "level3",
                 "level4", "siblingcount", "querytermcoverage", "jaccard"]

importance_df = pd.DataFrame({
    'feature': feature_names,
    'importance': feature_importances
}).sort_values(by='importance', ascending=False)

print(importance_df)


# Testing the Model and Evaluating
# Path to your test data CSV file
test_data_path = 'test_data_edited.csv'

# Run the relevance tests
evaluation_results = run_relevance_tests(
    relevance_data_filename=test_data_path,
    rankers=rankers,
    l2r_ranker=l2r_ranker,
    k=20
)

# You can now access the results
for ranker_name, scores in evaluation_results.items():
    print(f"Ranker: {ranker_name}")
    print(f"Average MAP: {scores['average_map']:.4f}")
    print(f"Average NDCG: {scores['average_ndcg']:.4f}\n")
