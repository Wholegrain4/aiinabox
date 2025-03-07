from flask import Flask, render_template, request, jsonify
import os
import re

# Your existing modules
from document_preprocessor import RegexTokenizer
from indexing import Indexer
from ranker import Ranker, BM25
from l2r import L2RFeatureExtractor, L2RRanker, MiscFunctionsL2R
from template_generator import TemplateGenerator

# -------------------------
# Flask & Global Setup
# -------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Load stopwords
with open('/app/front_end/stopwords.txt', 'r', encoding='utf-8') as f:
    stop_words = set(f.read().splitlines())

# Tokenizer
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

# Initialize rankers
bm25_scorer = BM25(index)
base_ranker = Ranker(
    index=index,
    document_preprocessor=tokenizer,
    stopwords=stop_words,
    scorer=bm25_scorer
)

# L2R
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

# Load model if available
try:
    l2r_ranker.load_model('/app/icd_10_search_eng_data/l2r_model.txt')
    print("Trained model loaded successfully.")
except Exception as e:
    print(f"Error loading trained model: {e}")

# Template generator
template_generator = TemplateGenerator()

# -------------------------
# Helper Functions
# -------------------------
def extract_terms_from_template(template_text):
    """ Extracts terms from a template using the TemplateGenerator’s AI. """
    terms = template_generator.extract_terms(template_text)
    print(f"Extracted terms: {terms}")
    return terms

def run_pipeline(user_input):
    """
    Encapsulates the template generation + L2R ranking pipeline.
    Returns a dict with 'verified_templates' and 'results', or 'error' on failure.
    """
    if not user_input:
        return {"error": "No input provided to pipeline."}

    # We gather all verified templates across personalities
    verified_templates = []
    all_extracted_terms = []

    # Try up to 4 personalities (0..3)
    for personality_index in range(4):
        # Step 1: fill the template
        filled_template = template_generator.generate_filled_template(
            personality_index=personality_index,
            user_input=user_input,
            temperature=0.1
        )
        if not filled_template:
            print(f"[Pipeline] Failed to generate template for personality {personality_index}")
            continue

        # Step 2: verify/correct the template
        verified_template = template_generator.check_outputs(
            response=filled_template,
            personality_index=personality_index,
            user_input=user_input,
            attempt=1,
            max_attempts=1
        )
        verified_templates.append({
            'personality_index': personality_index,
            'template': verified_template
        })

        # Step 3: extract terms for search
        extracted_terms = extract_terms_from_template(verified_template)
        all_extracted_terms.extend(extracted_terms)

    if not all_extracted_terms:
        return {
            "error": "No relevant terms found in the templates.",
            "verified_templates": verified_templates
        }

    # Construct new query from extracted terms (unique)
    new_query = ' '.join(set(all_extracted_terms))

    # Step 4: run the L2R ranker
    try:
        ranked_docs = l2r_ranker.query(new_query, k=15)
    except Exception as e:
        return {"error": f"Ranking error: {e}"}

    # Step 5: Retrieve doc data
    results = []
    for docid, score in ranked_docs:
        doc_metadata = index.document_metadata.get(docid, {})
        title = doc_metadata.get('title', 'No Title')
        snippet = doc_metadata.get('text', '')[:400] + '...'
        url = doc_metadata.get('url', '#')
        results.append({
            'docid': docid,
            'title': title,
            'snippet': snippet,
            'url': "https://www.icd10data.com" + url,
            'score': round(score, 2)
        })

    # Return everything
    return {
        "verified_templates": verified_templates,
        "results": results
    }

# -------------------------
# Routes
# -------------------------
@app.route('/')
def home():
    """Simple home page with a search box."""
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    """Handles a typed search query from the user."""
    query = request.form.get('query', '').strip()
    if not query:
        return render_template('index.html', error="Please enter a query.")

    pipeline_result = run_pipeline(query)
    if 'error' in pipeline_result:
        # If there's an error or no relevant terms
        return render_template('index.html',
                               error=pipeline_result['error'],
                               query=query,
                               verified_templates=pipeline_result.get('verified_templates', []))

    # Otherwise render results
    return render_template('index.html',
                           query=query,
                           results=pipeline_result['results'],
                           verified_templates=pipeline_result['verified_templates'])

@app.route('/api/transcript', methods=['POST'])
def handle_transcript():
    """
    Receives JSON posted by your scribe_consumer (or any client).
    JSON structure example:
        {
          "timestamp": "20250307_092655",
          "filename": "transcript_20250307_092655.txt",
          "transcript": "some transcribed text..."
        }
    """
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON payload"}), 400

        transcript = data.get("transcript", "").strip()
        if not transcript:
            return jsonify({"error": "No 'transcript' field in JSON"}), 400

        # Optionally do something with timestamp/filename
        timestamp = data.get("timestamp")
        filename = data.get("filename")

        # Run the pipeline on the transcript
        pipeline_result = run_pipeline(transcript)

        if "error" in pipeline_result:
            # Return pipeline error as JSON, status=200 or 400
            return jsonify({
                "error": pipeline_result["error"],
                "verified_templates": pipeline_result.get("verified_templates", [])
            }), 200

        # Return the pipeline results in JSON
        return jsonify({
            "status": "ok",
            "timestamp": timestamp,
            "filename": filename,
            "verified_templates": pipeline_result["verified_templates"],
            "results": pipeline_result["results"]
        }), 200

    except Exception as e:
        print(f"Error in /api/transcript route: {e}")
        return jsonify({"error": str(e)}), 500

# -------------------------
# Main Entry
# -------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
