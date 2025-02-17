import json

edge_list = []

with open('output.jsonl', 'r') as f:
    count = 0
    for line in f:
        doc = json.loads(line)
        docid = doc.get('docid', '').upper()
        mentions = [m.upper() for m in doc.get('mentions', [])]
        count += 1
        # print the progress percentage in terms of number of lines processed
        print(f"Processing percentage: {count} of a total of 61672 {round(count / 61672 * 100, 2)}%")
        for mention in mentions:
            # Edge from docid to mention
            edge_list.append((docid, mention))

# Save the edge list to a file
with open('edgelist.csv', 'w') as f:
    for edge in edge_list:
        f.write(f"{edge[0]},{edge[1]}\n")
