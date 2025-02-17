import json
import os

# Read in the link_array.json file
with open('link_array.json') as f:
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

with open('sorted_links.txt', 'w') as f:
    for link in sorted_links:
        f.write(link + '\n')

# Get all of the names of the files in the AI_Knowledge_Base folder without the .txt extension
files = os.listdir('AI_Knowledge_Base')
files = [file[:-4] for file in files]

# sort the files
sorted_files = sorted(files)

# save the sorted files to a new file
with open('sorted_files.txt', 'w') as f:
    for file in sorted_files:
        f.write(file + '\n')




# save first 1000 lines for both sorted_files and sorted_links
with open('sorted_files.txt') as f:
    sorted_files = [next(f).strip() for x in range(1000)]

with open('sorted_links.txt') as f:
    sorted_links = [next(f).strip() for x in range(1000)]

# save the first 1000 lines to new files
with open('sorted_files_1000.txt', 'w') as f:
    for file in sorted_files:
        f.write(file + '\n')

with open('sorted_links_1000.txt', 'w') as f:
    for link in sorted_links:
        f.write(link + '\n')

