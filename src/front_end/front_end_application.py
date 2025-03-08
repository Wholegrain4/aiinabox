from flask import Flask, render_template, request, jsonify
import os
from document_preprocessor import RegexTokenizer
from indexing import Indexer
from ranker import Ranker, BM25
from l2r import L2RFeatureExtractor, L2RRanker, MiscFunctionsL2R
from template_generator import TemplateGenerator

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["TEMPLATES_AUTO_RELOAD"] = True

# -------------------------------------------------------
# 1) In-memory store of transcripts & pipeline results
#    (In production, you'd use a real DB.)
# -------------------------------------------------------
TRANSCRIPTS_STORE = []  # each item: { 'timestamp', 'filename', 'transcript', 'verified_templates', 'results', 'error' }

# -------------------------------------------------------
# 2) Setup & initialization
# -------------------------------------------------------
with open('/app/front_end/stopwords.txt', 'r', encoding='utf-8') as f:
    stop_words = set(f.read().splitlines())

tokenizer = RegexTokenizer(stopwords=stop_words)

index_directory = '/app/icd_10_index_dir'
title_index_directory = '/app/icd_10_title_index_dir'

print("Loading main index...")
index = Indexer.load_index(index_directory)
print("Main index loaded.")

print("Loading title index...")
title_index = Indexer.load_index(title_index_directory)
print("Title index loaded.")

bm25_scorer = BM25(index)
base_ranker = Ranker(
    index=index,
    document_preprocessor=tokenizer,
    stopwords=stop_words,
    scorer=bm25_scorer
)

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

try:
    l2r_ranker.load_model('/app/icd_10_search_eng_data/l2r_model.txt')
    print("Trained model loaded successfully.")
except Exception as e:
    print(f"Error loading trained model: {e}")

template_generator = TemplateGenerator()

# -------------------------------------------------------
# 3) Pipeline helper
# -------------------------------------------------------
def run_pipeline(user_input):
    if not user_input:
        return {"error": "No input provided to pipeline."}

    verified_templates = []
    all_extracted_terms = []

    for personality_index in range(4):
        filled_template = template_generator.generate_filled_template(
            personality_index=personality_index,
            user_input=user_input,
            temperature=0.1
        )
        if not filled_template:
            print(f"[Pipeline] Failed to generate template {personality_index}")
            continue

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

        # Extract terms
        terms = template_generator.extract_terms(verified_template)
        all_extracted_terms.extend(terms)

    if not all_extracted_terms:
        return {
            "error": "No relevant terms found in the templates.",
            "verified_templates": verified_templates
        }

    new_query = ' '.join(set(all_extracted_terms))
    try:
        ranked_docs = l2r_ranker.query(new_query, k=15)
    except Exception as e:
        return {"error": f"Ranking error: {e}"}

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

    return {
        "verified_templates": verified_templates,
        "results": results
    }

# -------------------------------------------------------
# 4) Routes
# -------------------------------------------------------
@app.route('/')
def home():
    """
    Displays the *most recent* transcript's pipeline results
    in the same two-column layout (RAG on the left, results on the right)
    but no search bar.
    """
    if TRANSCRIPTS_STORE:
        last_transcript = TRANSCRIPTS_STORE[-1]
        print(last_transcript)
        error = last_transcript.get("error")
        verified_templates = last_transcript.get("verified_templates")
        results = last_transcript.get("results")
    else:
        error = None
        verified_templates = None
        results = None

    return render_template(
        'index.html',
        error=error,
        verified_templates=verified_templates,
        results=results
    )

@app.route('/api/transcript', methods=['POST'])
def handle_transcript():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON payload"}), 400

        txt = data.get("transcript", "").strip()
        if not txt:
            return jsonify({"error": "No 'transcript' field"}), 400

        timestamp = data.get("timestamp")
        filename = data.get("filename")

        pipeline_result = run_pipeline(txt)

        print(pipeline_result)

        record = {
            "timestamp": timestamp,
            "filename": filename,
            "transcript": txt,
            "verified_templates": pipeline_result.get("verified_templates"),
            "results": pipeline_result.get("results"),
        }

        print(record)

        if "error" in pipeline_result:
            record["error"] = pipeline_result["error"]

        # Store in the transcripts
        TRANSCRIPTS_STORE.append(record)

        print(TRANSCRIPTS_STORE)

        # Render the updated page directly:
        return render_template(
            'index.html',
            error=record.get("error"),
            verified_templates=record.get("verified_templates"),
            results=record.get("results")
        )

    except Exception as e:
        print(f"Error in /api/transcript: {e}")
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------
# Main
# -------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
