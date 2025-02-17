import string
import nltk
from enum import Enum
from collections import Counter, defaultdict
import json
import os
import chardet
import math
import pandas as pd
import numpy as np
import lightgbm
import csv
import re
from document_preprocessor import Tokenizer
from indexing import InvertedIndex
from misc_tools import MiscTools
from network_features import NetworkFeatures
from document_preprocessor import RegexTokenizer
from indexing import Indexer, IndexType
from ranker import Ranker, BM25, TF_IDF, WordCountCosineSimilarity, DirichletLM, PivotedNormalization
from l2r import L2RFeatureExtractor, L2RRanker, MiscFunctionsL2R


################################
#### Set Up the Corpus Info ####
################################

#### Import the Link Array ####
with open("/app/icd_10_code_jsons/icd_10_code_links.json") as f:
    link_array = json.load(f)

# Count the number of links
num_links = len(link_array[0])
print("Number of links in the corpus: ", num_links)

# Count the number of unique links
unique_links = set(link_array[0])
num_unique_links = len(unique_links)
print("Number of unique links in the corpus: ", num_unique_links)

# Sort the links and save them to a new file
sorted_links = sorted(unique_links)

with open('/app/icd_10_search_eng_data/sorted_links.txt', 'w') as f:
    for link in sorted_links:
        f.write(link + '\n')

# Get all of the names of the files in the AI_Knowledge_Base folder without the .txt extension
files = os.listdir('/app/icd_10_codes_clean')
files = [file[:-4] for file in files]

# sort the files
sorted_files = sorted(files)

# save the sorted files to a new file
with open('/app/icd_10_search_eng_data/sorted_files.txt', 'w') as f:
    for file in sorted_files:
        f.write(file + '\n')


################################
#### Set Up the Corpus      ####
################################
my_misc_tools = MiscTools()

# Specify the file paths
titles_file = '/app/icd_10_search_eng_data/sorted_files.txt'
links_file = '/app/icd_10_search_eng_data/sorted_links.txt'
output_file = '/app/icd_10_search_eng_data/output.jsonl'

# Detect encoding
encoding = my_misc_tools.detect_encoding(titles_file)
print(f"Detected encoding for {titles_file}: {encoding}")

# If encoding is not detected, use a default encoding
encoding = 'ISO-8859-1'

# Initialize the set of all codes
all_codes = set()

# Read the Titles
try:
    with open(titles_file, 'r', encoding=encoding, errors='replace') as f:
        titles = [line.strip() for line in f if line.strip()]
except Exception as e:
    print(f"Error reading {titles_file}: {e}")
    titles = []

# Extract codes from titles and add to all_codes
for title in titles:
    code = title.split(' ')[0].strip()
    all_codes.add(code.lower())  # Assuming case-insensitive codes

# Read and Clean the Links
try:
    with open(links_file, 'r', encoding=encoding, errors='replace') as f:
        links = []
        seen = set()
        for line in f:
            link = line.strip()
            if link and link not in seen:
                seen.add(link)
                links.append(link)
except Exception as e:
    print(f"Error reading {links_file}: {e}")
    links = []

# Create a Mapping from Code to Link and add codes to all_codes
link_dict = {}
for link in links:
    code = link.strip().split('/')[-1]
    link_dict[code] = link
    all_codes.add(code.lower())

# Process Each Title and Generate JSON Objects
with open(output_file, 'w', encoding='ISO-8859-1') as outfile:
    count = 0
    for title in titles:
        # Extract the code from the title (assumes code is the first word)
        code = title.split(' ')[0].strip()

        # Get the corresponding link
        link = link_dict.get(code, 'Link not found')

        # Sanitize the title to create a valid filename
        filename = my_misc_tools.sanitize_filename(title) + '.txt'

        # Build the full path to the text file in AI_Knowledge_Base directory
        text_filename = os.path.join('/app/icd_10_codes_clean', filename)

        if os.path.exists(text_filename):
            try:
                with open(text_filename, 'r', encoding='ISO-8859-1', errors='replace') as text_file:
                    text = text_file.read().strip()
            except Exception as e:
                print(f"Error reading {text_filename}: {e}")
                text = 'Text file could not be read'
        else:
            text = 'Text file not found'

        # Find mentions of other codes in the text
        # Tokenize the text
        tokens = re.findall(r'\b\w+(?:\.\w+)?\b', text)
        tokens = [token.lower() for token in tokens]

        # Find intersection with all_codes, excluding the code of the current document
        mentions = set(tokens) & all_codes
        mentions.discard(code.lower())  # Remove the code of the current document

        # Convert mentions to a sorted list
        mentions = sorted(mentions)

        # Create the JSON object
        json_obj = {
            'title': title,
            'link': link,
            'text': text,
            'mentions': mentions,
            'docid': code
        }

        count += 1

        # print the progress in terms of number of lines processed
        print(f"Processed: {count} of a total of {len(titles)} {round((titles.index(title) + 1) / len(titles) * 100, 2)}%")

        # Write the JSON object to the JSONL file
        json_line = json.dumps(json_obj, ensure_ascii=False)
        outfile.write(json_line + '\n')

print(f"JSONL file '{output_file}' has been created successfully.")

################################
#### Create the Edge List   ####
################################
edge_list = []

with open('/app/icd_10_search_eng_data/output.jsonl', 'r') as f:
    count = 0
    for line in f:
        doc = json.loads(line)
        docid = doc.get('docid', '').upper()
        mentions = [m.upper() for m in doc.get('mentions', [])]
        count += 1
        # print the progress percentage in terms of number of lines processed
        print(f"Processing percentage: {count} of a total of 17057 {round(count / 17057 * 100, 2)}%")
        for mention in mentions:
            # Edge from docid to mention
            edge_list.append((docid, mention))

# Save the edge list to a file
with open('/app/icd_10_search_eng_data/edgelist.csv', 'w') as f:
    for edge in edge_list:
        f.write(f"{edge[0]},{edge[1]}\n")

################################
#### Build Network Stats    ####
################################
# Initialize the loader
loader = NetworkFeatures()
file_path = '/app/icd_10_search_eng_data/edgelist.csv'

# Preview the network file
loader.preview_network_file(file_path, num_lines=5)

# Load the network
network = loader.load_network(file_path)

# Calculate PageRank scores
pagerank_scores = loader.calculate_page_rank(network, damping_factor=0.85, iterations=100)

# Print the top 10 PageRank scores with their docids
pagerank_df = pd.DataFrame({
    'docid': network.names,
    'pagerank': pagerank_scores
}).sort_values(by='pagerank', ascending=False)
print("Top 10 PageRank scores:")
print(pagerank_df.head(10))

# Calculate HITS scores
hub_scores, authority_scores = loader.calculate_hits(network)

# Create dataframes for hub and authority scores
hub_df = pd.DataFrame({
    'docid': network.names,
    'hub_score': hub_scores
}).sort_values(by='hub_score', ascending=False)
authority_df = pd.DataFrame({
    'docid': network.names,
    'authority_score': authority_scores
}).sort_values(by='authority_score', ascending=False)

# Get all network statistics and save to CSV
network_statistics = loader.get_all_network_statistics(network)
network_statistics.to_csv('/app/icd_10_search_eng_data/network_statistics.csv', index=False)

################################
#### Create Search Index    ####
################################
# Load stop words from file

with open('/app/stopwords.txt', 'r', encoding='utf-8') as f:
    stop_words = f.read().splitlines()
stop_words = set(stop_words)

# Initialize the tokenizer
tokenizer = RegexTokenizer(stopwords=stop_words)

# Paths to the index directories
index_directory = '/app/icd_10_index_dir'
title_index_directory = '/app/icd_10_title_index_dir'

# Path to the dataset
dataset_path = '/app/icd_10_search_eng_data/output.jsonl'

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

################################
#### Init Scorers and Rankers ##
################################

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
    docid_to_network_features=MiscFunctionsL2R().load_network_features("/app/icd_10_search_eng_data/network_statistics.csv")
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
training_data_path = '/app/train_data_edited.csv'

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
l2r_ranker.save_model('/app/icd_10_search_eng_data/l2r_model.txt')
print("Model saved to l2r_model.txt")

