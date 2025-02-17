library(RSelenium)
library(wdman)
library(rvest)
library(stringr)
library(jsonlite)
library(doParallel)
library(foreach)

# --- Helper Functions ---
create_driver <- function(port_num) {
  # Create a unique user data directory for this driver session
  chrome_opts <- list(
    chromeOptions = list(
      args = c("--disable-gpu",
               "--blink-settings=imagesEnabled=false",
               "--no-sandbox",
               "--disable-dev-shm-usage",
               "--headless",
               "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")
    )
  )
  
  # Try to create the RSelenium driver and, if it fails, print the error message
  rD <- tryCatch({
    rsDriver(
      browser = "chrome",
      chromever = "133.0.6943.53",
      port = port_num,
      extraCapabilities = chrome_opts,
      verbose = FALSE
    )
  }, error = function(e) {
    message("Error creating rsDriver on port ", port_num, ": ", e$message)
    stop(e)
  })
  
  return(rD)
}

split_into_chunks <- function(vec, n) {
  # Validate n
  if (!is.numeric(n) || length(n) != 1 || n < 1) {
    stop("'n' must be a single integer >= 1")
  }
  
  len <- length(vec)
  # If your vector is empty, return n empty chunks (or decide how you want to handle it)
  if (len == 0) {
    return(vector("list", n))
  }
  
  # Compute the size of each chunk (ceiling so as not to lose elements)
  chunk_size <- ceiling(len / n)
  result <- vector("list", n)
  
  start <- 1
  for (i in seq_len(n)) {
    end <- min(start + chunk_size - 1, len)
    if (start > len) {
      # If we've already used up all elements, store an empty vector
      result[[i]] <- vector(mode(vec), 0)
    } else {
      result[[i]] <- vec[start:end]
    }
    start <- end + 1
  }
  
  result
}

# --- Step 1: Get All Main Links from the Codes Page ---

base_url <- "https://www.icd10data.com"

## 1. Create the .local structure using wdman's selenium call
message("=== Calling wdman::selenium() to create .local structure ===")
invisible(selenium(geckover = NULL, iedrver = NULL, phantomver = NULL))

# 2. Define the target parent directory
targetParent <- file.path("~", ".local", "share", "binman_chromedriver", "linux64")

# 4. Show the source directory contents
sourceFolder <- file.path("/app", "bin", "133.0.6943.53")

# 5. Copy the entire folder (133.0.6943.53) if target exists
if (dir.exists(targetParent)) {
  copied <- file.copy(from = sourceFolder, to = targetParent, recursive = TRUE, overwrite = TRUE)
  
  if (copied) {
    license_files <- list.files(
      path = targetParent,
      pattern = "^LICENSE\\.chromedriver$",
      recursive = TRUE,
      full.names = TRUE
    )
    if (length(license_files) > 0) {
      file.remove(license_files)
    } else {
      message("...")
    }
    
  } else {
    message("Failed to copy folder '133.0.6943.53' from ", sourceFolder, " to ", targetParent)
  }
} else {
  message("Target directory does not exist: ", targetParent, ". Folder not copied.")
}

# Launch a dedicated RSelenium session to fetch the main links
main_port <- 4444L  # choose a port that is not used by parallel sessions
rD_main <- create_driver(main_port)
remDr_main <- invisible(rD_main$client) 
Sys.sleep(0.5)
# Navigate to the Codes page
remDr_main$navigate(paste0(base_url, "/ICD10CM/Codes"))
Sys.sleep(0.5)  # wait for the page to load

# Get the page source and parse it
page_source <- remDr_main$getPageSource()[[1]]
Sys.sleep(0.5)
page_html <- read_html(page_source)
Sys.sleep(0.5)

# Extract the main links (the anchor tags inside the ul with class "ulPopover")
ul <- html_nodes(page_html, "ul.ulPopover")
Sys.sleep(0.5)
a_nodes <- html_nodes(ul, "a")
Sys.sleep(0.5)
main_links <- html_attr(a_nodes, "href")

main_links <- main_links[1:10]

# Optionally, print how many main links were found
message(sprintf("Found %d main links.", length(main_links)))

# Close the main links driver
remDr_main$close()
rD_main$server$stop()

# --- Step 2: Parallel Processing of Each Main Link ---

num_sessions <- 5
link_chunks <- split_into_chunks(main_links, num_sessions)
ports <- c(4441L, 4442L, 4443L, 4444L, 4445L)

cl <- makeCluster(num_sessions)
registerDoParallel(cl)

# Define a shared log file (ensure the path is writable in Docker)
log_file <- "/app/icd_10_code_jsons/scrape.log"
# Optionally, clear the previous log file:
if (file.exists(log_file)) file.remove(log_file)

chunk_results <- foreach(i = seq_along(link_chunks),
                         .packages = c("RSelenium", "rvest", "stringr")) %dopar% {
                           
                           # Define a logging function for the worker
                           log_message <- function(msg) {
                             cat(sprintf("[%s] Worker %d: %s\n", Sys.time(), i, msg),
                                 file = log_file, append = TRUE)
                           }
                           
                           log_message("Starting processing of assigned chunk.")
                           
                           rD <- create_driver(ports[i])
                           remDr <- invisible(rD$client)
                           
                           scraped_links <- c()
                           random_prob <- c(0.1, 0.05, 0.3, 0.05, 0.05, 0.3, 0.05, 0.025, 0.025, 0.05)
                           num_links <- length(link_chunks[[i]])
                           
                           for (j in seq_along(link_chunks[[i]])) {
                             link <- link_chunks[[i]][j]
                             random_wait <- sample(1:10, 1, replace = TRUE, prob = random_prob)
                             Sys.sleep(random_wait)
                             Sys.sleep(1.5)
                             
                             full_url <- paste0(base_url, link)
                             log_message(sprintf("Navigating to %s", full_url))
                             remDr$navigate(full_url)
                             
                             page_source <- remDr$getPageSource()[[1]]
                             page_html <- read_html(page_source)
                             
                             sub_links <- page_html %>%
                               html_nodes("div.body-content") %>%
                               html_nodes("a") %>%
                               html_attr("href")
                             
                             
                             scraped_links <- c(scraped_links, sub_links)
                             log_message(sprintf("Completed %d of %d main links", j, num_links))
                           }
                           
                           remDr$close()
                           rD$server$stop()
                           log_message("Worker finished processing its chunk.")
                           
                           scraped_links
                         }

stopCluster(cl)

all_links <- unlist(chunk_results)
link_array_sub <- all_links[str_count(all_links, "/") == 6]

result_list <- list(link_array_sub)
exportJson <- toJSON(result_list, pretty = TRUE)
write(exportJson, "/app/icd_10_code_jsons/icd_10_code_links.json")