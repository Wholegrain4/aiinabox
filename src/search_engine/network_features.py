from pandas import DataFrame
from sknetwork.data import from_edge_list
from sknetwork.ranking import PageRank, HITS
import time
import gzip
import numpy as np

class NetworkFeatures:
    """
    A class to help generate network features such as PageRank scores, HITS hub score, and HITS authority scores.
    This class uses the scikit-network library https://scikit-network.readthedocs.io to calculate node ranking values.
    """

    def preview_network_file(self, network_filename: str, num_lines: int = 5):
        """
        Opens the network file and prints the first few rows.

        Args:
            network_filename: The name of a .csv or .csv.gz file containing an edge list
            num_lines: The number of lines to preview from the file
        """
        if network_filename.endswith('.gz'):
            with gzip.open(network_filename, 'rt') as f:
                for _ in range(num_lines):
                    print(f.readline().strip())
        else:
            with open(network_filename, 'r') as f:
                for _ in range(num_lines):
                    print(f.readline().strip())

    def load_network(self, network_filename: str):
        """
        Loads the network from the specified file and returns the network.

        Args:
            network_filename: The name of a .csv or .csv.gz file containing an edge list

        Returns:
            The loaded network from sknetwork
        """

        edges = []

        start_time = time.time()
        if network_filename.endswith('.gz'):
            with gzip.open(network_filename, 'rt') as f:
                for line in f:
                    try:
                        row, col = line.strip().split(',')
                        edges.append((row, col))
                    except ValueError:
                        continue
            print("Time taken to read the network:", time.time() - start_time)

            start_time = time.time()
            graph = from_edge_list(edges, directed=True)
            print("Time taken to load the network:", time.time() - start_time)
        else:
            with open(network_filename, 'r') as f:
                for line in f:
                    try:
                        row, col = line.strip().split(',')
                        edges.append((row, col))
                    except ValueError:
                        continue
            print("Time taken to read the network:", time.time() - start_time)
            start_time = time.time()
            graph = from_edge_list(edges, directed=True)
            print("Time taken to load the network:", time.time() - start_time)

        print("Graph loaded with", graph.adjacency.shape[0], "nodes.")
        return graph

    def calculate_page_rank(self, graph, damping_factor=0.85, iterations=100) -> list[float]:
        """
        Calculates the PageRank scores for the provided network and returns the PageRank values for all nodes.

        Args:
            graph: A graph from sknetwork
            damping_factor: The complement of the teleport probability for the random walker
                For example, a damping factor of .8 has a .2 probability of jumping after each step.
            iterations: The maximum number of iterations to run when computing PageRank

        Returns:
            The PageRank scores for all nodes in the network (array-like)
        """
        pagerank = PageRank(damping_factor=damping_factor, n_iter=iterations)
        print("Calculating PageRank")
        scores = pagerank.fit_predict(graph.adjacency)
        return scores.tolist()

    def calculate_hits(self, graph) -> tuple[list[float], list[float]]:
        """
        Calculates the hub scores and authority scores using the HITS algorithm for the provided network.

        Args:
            graph: A graph from sknetwork

        Returns:
            The hub scores and authority scores (in that order) for all nodes in the network
        """
        hits = HITS()
        print("Calculating HITS")
        hits.fit(graph.adjacency)
        authority_scores = hits.scores_.tolist()

        # For hub scores, use the adjacency transpose
        hits_hub = HITS()
        hits_hub.fit(graph.adjacency.transpose())
        hub_scores = hits_hub.scores_.tolist()

        return (hub_scores, authority_scores)

    def get_all_network_statistics(self, graph) -> DataFrame:
        """
        Calculates the PageRank, hub scores, and authority scores using the HITS algorithm
        for the provided network and returns a pandas DataFrame.

        Args:
            graph: A graph from sknetwork

        Returns:
            A pandas DataFrame with columns 'docid', 'pagerank', 'authority_score', and 'hub_score'
        """
        # Calculate PageRank
        pagerank_scores = self.calculate_page_rank(graph)

        # Calculate HITS
        hub_scores, authority_scores = self.calculate_hits(graph)

        # Get docids from graph.names
        docids = graph.names

        df = DataFrame({
            'docid': docids,
            'pagerank': pagerank_scores,
            'authority_score': authority_scores,
            'hub_score': hub_scores
        })

        return df
