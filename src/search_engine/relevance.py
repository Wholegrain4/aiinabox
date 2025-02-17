import csv
import math


def map_score(search_result_relevances: list[int], cut_off: int = 10):
    """
    Calculates the mean average precision score given a list of labeled search results, where
    each item in the list corresponds to a document that was retrieved and is rated as 0 (not relevant),
    1 (not as relevant), 2 (relevant), or 3 (most relevant). Both 2 and 3 are treated as relevant.

    Args:
        search_result_relevances: A list of integers (0, 1, 2, or 3) representing the relevance of each search result.
        cut_off: The search result rank to stop calculating MAP.

    Returns:
        The MAP score.
    """
    search_result_relevances = search_result_relevances[:cut_off]

    num_rel_docs = 0
    total_precision = 0.0

    for i, relevance in enumerate(search_result_relevances, start=1):
        if relevance >= 1:  # Treat scores 2 and 3 as relevant
            num_rel_docs += 1
            pak = num_rel_docs / i
            total_precision += pak

    if num_rel_docs == 0:
        return 0.0
    else:
        avg_precision = total_precision / num_rel_docs
        return avg_precision

def ndcg_score(search_result_relevances: list[float],
               ideal_relevance_score_ordering: list[float], cut_off: int = 10):
    """
    Calculates the normalized discounted cumulative gain (NDCG) given lists of relevance scores.
    Relevance scores can be ints or floats, depending on how the data was labeled for relevance.

    Args:
        search_result_relevances: A list of relevance scores for the results returned by your ranking function
            in the order in which they were returned.
        ideal_relevance_score_ordering: The list of relevance scores for results for a query, sorted by relevance score
            in descending order.
        cut_off: The default cut-off is 10.

    Returns:
        The NDCG score as a float.
    """

    search_result_relevances = search_result_relevances[:cut_off]
    ideal_relevance_score_ordering = ideal_relevance_score_ordering[:cut_off]

    # Calculate DCG
    dcg_score = 0.0
    for i, rel in enumerate(search_result_relevances):
        numerator = (2 ** rel) - 1
        denominator = math.log2(i + 2)  # idx + 2 because idx starts from 0
        dcg_score += numerator / denominator

    # Calculate IDCG
    idcg_score = 0.0
    for i, rel in enumerate(ideal_relevance_score_ordering):
        numerator = (2 ** rel) - 1
        denominator = math.log2(i + 2)
        idcg_score += numerator / denominator

    # Avoid zero
    if idcg_score == 0:
        return 0.0

    # Calculate NDCG
    ndcg = dcg_score / idcg_score
    return ndcg




def run_relevance_tests(relevance_data_filename: str, rankers: dict, l2r_ranker, k=20) -> dict:
    """
    Runs relevance tests and computes MAP and NDCG scores for each ranker.

    Args:
        relevance_data_filename (str): Path to the test data CSV file.
        rankers (dict): A dictionary of base rankers (e.g., BM25, TF_IDF).
        l2r_ranker: The trained L2RRanker instance.
        k (int): The number of top documents to consider for evaluation.

    Returns:
        dict: A dictionary containing average MAP and NDCG scores per ranker.
    """
    # Initialize an empty dictionary to hold the test data
    test_query_to_document_relevance_scores = {}

    # Read the test data from the CSV file
    with open(relevance_data_filename, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            query = row['Query'].strip()
            docid = row['docid'].strip()
            relevance = int(row['Rel Score'])
            
            # Add the data to the dictionary
            if query not in test_query_to_document_relevance_scores:
                test_query_to_document_relevance_scores[query] = {}
            test_query_to_document_relevance_scores[query][docid] = relevance

    # Get the list of test queries
    print(f"relevant data: {test_query_to_document_relevance_scores}")
    test_queries = list(test_query_to_document_relevance_scores.keys())

    # Prepare per-ranker MAP and NDCG scores
    per_ranker_map_scores = {name: [] for name in rankers.keys()}
    per_ranker_map_scores['L2R'] = []
    per_ranker_ndcg_scores = {name: [] for name in rankers.keys()}
    per_ranker_ndcg_scores['L2R'] = []

    # For each test query
    for test_query in test_queries:
        # Get the relevance judgments for this query
        relevance_judgments = test_query_to_document_relevance_scores[test_query]
        
        # Prepare ideal ranking for NDCG
        ideal_relevances = sorted(relevance_judgments.values(), reverse=True)
        
        # For each ranker
        for ranker_name in list(rankers.keys()) + ['L2R']:
            if ranker_name == 'L2R':
                # Use L2R model
                results = l2r_ranker.query(test_query, k=k)
                # print(f"Results for query '{test_query}': {results}")
            else:
                # Use base ranker
                results = rankers[ranker_name].query(test_query, k=k)
            
            # Get retrieved docids and their relevances
            retrieved_docids = [docid for docid, score in results]
            retrieved_relevances = [relevance_judgments.get(docid, 0) for docid in retrieved_docids]
            
            # Calculate MAP score for this query
            map_score_value = map_score(retrieved_relevances)
            per_ranker_map_scores[ranker_name].append(map_score_value)
            
            # Calculate NDCG score for this query
            ndcg_score_value = ndcg_score(retrieved_relevances, ideal_relevances)
            per_ranker_ndcg_scores[ranker_name].append(ndcg_score_value)
    
    # After processing all queries, compute average MAP and NDCG per ranker
    results = {}
    for ranker_name in per_ranker_map_scores.keys():
        avg_map = sum(per_ranker_map_scores[ranker_name]) / len(per_ranker_map_scores[ranker_name]) if per_ranker_map_scores[ranker_name] else 0.0
        avg_ndcg = sum(per_ranker_ndcg_scores[ranker_name]) / len(per_ranker_ndcg_scores[ranker_name]) if per_ranker_ndcg_scores[ranker_name] else 0.0
        results[ranker_name] = {'average_map': avg_map, 'average_ndcg': avg_ndcg}

    return results
