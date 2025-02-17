from network_features import NetworkFeatures
from pandas import DataFrame

# Initialize the loader
loader = NetworkFeatures()
file_path = 'edgelist.csv'

# Preview the network file
loader.preview_network_file(file_path, num_lines=5)

# Load the network
network = loader.load_network(file_path)

# Calculate PageRank scores
pagerank_scores = loader.calculate_page_rank(network, damping_factor=0.85, iterations=100)

# Print the top 10 PageRank scores with their docids
pagerank_df = DataFrame({
    'docid': network.names,
    'pagerank': pagerank_scores
}).sort_values(by='pagerank', ascending=False)
print("Top 10 PageRank scores:")
print(pagerank_df.head(10))

# Calculate HITS scores
hub_scores, authority_scores = loader.calculate_hits(network)

# Create dataframes for hub and authority scores
hub_df = DataFrame({
    'docid': network.names,
    'hub_score': hub_scores
}).sort_values(by='hub_score', ascending=False)
authority_df = DataFrame({
    'docid': network.names,
    'authority_score': authority_scores
}).sort_values(by='authority_score', ascending=False)

# Print the top 10 hub and authority scores
print("Top 10 Hub scores:")
print(hub_df.head(10))
print("Top 10 Authority scores:")
print(authority_df.head(10))

# Get all network statistics and save to CSV
network_statistics = loader.get_all_network_statistics(network)
network_statistics.to_csv('network_statistics.csv', index=False)
