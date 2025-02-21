from flask import Flask, render_template, request
import os
import re
from document_preprocessor import RegexTokenizer
from indexing import Indexer
from ranker import Ranker, BM25
from l2r import L2RFeatureExtractor, L2RRanker, MiscFunctionsL2R
from template_generator import TemplateGenerator

# Initialize the Flask app
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["TEMPLATES_AUTO_RELOAD"] = True
# Load stop words
with open('/app/front_end/stopwords.txt', 'r', encoding='utf-8') as f:
    stop_words = set(f.read().splitlines())

# Initialize the tokenizer
tokenizer = RegexTokenizer(stopwords=stop_words)

# Paths to the index directories
index_directory = '/app/icd_10_index_dir'
title_index_directory = '/app/icd_10_title_index_dir'

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

# Load the trained model
try:
    l2r_ranker.load_model('/app/icd_10_search_eng_data/l2r_model.txt')
    print("Trained model loaded successfully.")
except Exception as e:
    print(f"Error loading trained model: {e}")

# Initialize the TemplateGenerator
template_generator = TemplateGenerator()



def extract_terms_from_template(template_text):
    """
    Uses the TemplateGenerator's extract_terms method to extract relevant terms from the filled template.
    """
    terms = template_generator.extract_terms(template_text)
    print(f"Extracted terms: {terms}")
    return terms


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    query = request.form.get('query', '').strip()
    if not query:
        return render_template('index.html', error="Please enter a query.")

    try:
        # Initialize lists to hold all verified templates and extracted terms
        verified_templates = []
        all_extracted_terms = []

        # Process all templates (indices from 0 to 3)
        for personality_index in range(4):
            # Use the TemplateGenerator to process the query
            filled_template = template_generator.generate_filled_template(
                personality_index=personality_index,
                user_input=query,
                temperature=0.1
            )

            print

            if not filled_template:
                print(f"Failed to generate the filled-out template for Personality {personality_index}")
                continue  # Skip to the next personality

            # Verify and correct the template
            verified_template = template_generator.check_outputs(
                response=filled_template,
                personality_index=personality_index,
                user_input=query,
                attempt=1,
                max_attempts=1
            )

            # Add the verified template to the list
            verified_templates.append({
                'personality_index': personality_index,
                'template': verified_template
            })

            # Extract relevant terms from the verified template using AI
            extracted_terms = extract_terms_from_template(verified_template)
            all_extracted_terms.extend(extracted_terms)

        if not all_extracted_terms:
            return render_template('index.html', error="No relevant terms found in the templates.")

        # Construct a new query using the extracted terms (remove duplicates)
        new_query = ' '.join(set(all_extracted_terms))

        # Use the L2R ranker to get the top results
        ranked_docs = l2r_ranker.query(new_query, k=15)

        # Retrieve document data
        results = []
        for docid, score in ranked_docs:
            # Retrieve document metadata
            doc_metadata = index.document_metadata.get(docid, {})
            title = doc_metadata.get('title', 'No Title')
            # Create a snippet with a maximum of 400 characters for better display
            snippet = doc_metadata.get('text', '')[:400] + '...'
            url = doc_metadata.get('url', '#')
            results.append({
                'docid': docid,
                'title': title,
                'snippet': snippet,
                'url': "https://www.icd10data.com" + url,
                'score': round(score, 2)
            })

    except Exception as e:
        print(f"Error during search: {e}")
        return render_template('index.html', error="An error occurred during search.")

    # Pass the verified templates to the template for display
    return render_template('index.html', results=results, query=query, verified_templates=verified_templates)

if __name__ == '__main__':
    app.run(debug= True, host='0.0.0.0', port=5000)