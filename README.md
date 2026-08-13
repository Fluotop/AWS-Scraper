# Supermarket Scraper
## Purpose
The purpose of this project is to track price data of products offered in the 2 supermarkets (Chedraui Kabeh and Superaki) closest to my home during my 1 year stay in Mexico. The goal was to learn DevOps using AWS, Terraform and github actions.
# Infrastructure
Every Tuesday when both stores offer extra discounts on fruit and vegetables a eventbridge schedule will trigger a lambda function which creates an EC2 instance that fetches the scraper scripts from Github. The scraper script dumps its data as parquet files in an S3 bucket structured by store, date and product category. After running the script the EC2 instance will either _SUCCESS or _FAILURE in the S3 bucket after which it auto terminates. An eventbridge rule scans the bucket for the message and on success will start a step function workflow or send an email on failure. 
Step function starts with a lambda that updates the glue catalog with the newly scraped data. On success 4 athena queries are run. Each query creates this weeks data needed for each page on the dashboard. After lambda aggregates the current weeks result to the historic results. At the end the html containing the dashboard is created and put in an S3 bucket. The html is then used in the personal website project.


<img width="761" height="877" alt="Untitled Diagram" src="https://github.com/user-attachments/assets/5114e70e-445c-45a5-b980-b91d3b43ac8d" />


# Lambda code
## Scraper Launcher
-	Initialize EC2 using Boto3 and direct all logs to central log file
-	Install a python env.
-	Fetch keys to access files on github from parameter store
-	Setup dependencies for chromium browser 
-	Install playwright using python
-	Run python scraper
-	Fetch ID of running EC2
-	Output logs
-	Terminate EC2

# Python scripts
## Category Manager
Fetches the available product categories from Chedraui and Superaki. Can store categories in duckDB or on AWS. Uses scraping logic explained below.
## Base scraper
Store independent script that sets default values. It creates a chromium session fetches the available categories per store. It fetches the URLs using exponential backoff if needed and can handle some error codes returned from Chedraui or Superaki. Failed URLs are skipped. 
## Chedraui Scraper
Sets parameters for specific store and fetch its region ID using playwright package. Setup a browser session using the region ID. Each subcategory is scraped in batches of 20 products matching what’s displayed on the website and in 5 sec intervals. All batches pass a checkout simulation which is needed to get accurate prices for the specific store. The returned JSON is parsed and useful info is put in tuples.
## SuperAki scraper
Similar as above but can be scraped directly without needing playwright. Pages directly provide correct info that can be stored.
# Storage
Tuples can be stored locally or on AWS by changing the settings in the main file.
## Local storage
A duckdb SQL database is created with following columns by local_storage.py:
-	Product_id
-	Store
-	Scrape_date
-	Name: name of product
-	Brand: brande of product
-	Maincat: name of the main product category
-	Cat: name of the product category
-	Subcat: name of the product subcategory (can be null)
-	CatID: Number of the category ID. This numeric code consists of 3 sets of numbers put together. 1 for maincat, 1 for cat and 1 for subcat
-	Image: link to an image of the product
-	Price: listed price
-	Pricewithoutdiscount: Default price
-	List_price: Default price backup
-	Is_available: flag 
-	Link: to product on store page
Primary key is (product_id, store, scrape_date)
## AWS
Tuples get put into a polars dataset with columns as above by AWS_storage.py. After a subcat is fully scraped it the polar datasets gets written to S3 in following directory ./scrape_date/store/subcat/
# Analysis
Can be done locally or on AWS and is based on the analysis done for Colruyt here (https://colruyt-prijzen.nasaj.be/)
## Local analysis
Query_local.py runs a query to enrich the data with 4 extra columns:
-	List_price_diff: list_price – list_price (from last week)
-	List_price_pct_change: % diff in list_price – list_price (from last week)
-	Price_diff: price – price (form last week)
-	Price_pct_change: % diff in price – price (from last week)
4 SQL queries are needed to retrieve data are needed for the dashboard. These are located under located under Terraform/lambda/SQL. The dashboard has 4 pages corresponding to these 4 queries:
-	List_price_increases: Top 20 products that increased in default price compared to last week.
-	List_price_decreases: Top 20 products that decreased in default price compared to last week.
-	Discounts: Top 20 products based on difference between list prices for previous and current week.
-	30d_avg_deals: Top 20 products based on the difference between the list price and the 30 day average price of the product.
## Dashboard_local.py 
AI generated using polars and plotly both of which I’m familiar with by dashboard_local.py. Creates 4 pages as above and displays the product image, a price history graph for the list price and price. Output seems correct based on in store checks and manual calculations.
## AWS analysis
Done with step functions. Athena runs the same query to enrich the data with the same 4 columns as the query_local.py script. After Athena runs the 4 SQL queries in the Terraform/lambda/SQL folder. The dashboard script is run after on EC2.

# Testing
-	Category_scraper: Moto is used to create dummy AWS S3 bucket. A test category is added.
-	Chedraui_scraper: a specific product needed values are checked against what they were on the date of creating this test script. Price is excluded as this is expected to be change. 
-	Superaki_scraper: same as above
-	Aws_storage: test writing product values to an s3 bucket. Moto creates mock infra.
-	Queries_local: conftest.py creates 2 weeks worth of fake products with changing prices. The query_local.py script is ran on this data and new calculated columns that are added are checked for numerical correctness.
-	Queries_aws: similar as above but with test infra created by moto 
# Automation
## Infrastructure as code (IaC)
All AWS resources used are coded in Terraform cloud. A module was created for tagging every resource in the project. Variables are set in the prod.auto.tfvars file.
## CI/CD
Deployment is not done manually but is automated through github actions (.github/workflows/deploy.yaml). The pipeline runs all tests upon deploy.
## Monitoring
AWS sends an email if the scraper script would fail to prevent EC2 instances to hang forever.










