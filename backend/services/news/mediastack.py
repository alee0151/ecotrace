import requests
import json
import time
import os
import pandas as pd

def fetch_mediastack_news_to_csv(access_key, keywords="coles", countries="au", start_date="2022-04-10", end_date="2026-04-10"):
    # With a paid plan, you can and should use HTTPS
    url = "https://api.mediastack.com/v1/news"
    
    limit = 100 
    offset = 0
    all_articles = []
    total_articles = None
    
    # Check if a partial download exists to resume without wasting API calls
    if os.path.exists("bhp_news_dataset.json"):
        with open("bhp_news_dataset.json", "r") as f:
            try:
                all_articles = json.load(f)
                offset = len(all_articles)
                print(f"Resuming from offset {offset} with {len(all_articles)} existing records.")
            except:
                pass
    
    print(f"Starting API fetch for keywords: '{keywords}'...")
    
    while True:
        # Mediastack hard limit prevention
        if offset >= 10000:
            print("WARNING: Reached Mediastack's maximum pagination offset of 10000.")
            print("To get more records, you must shrink your date ranges into smaller chunks (e.g., month by month).")
            break
            
        params = {
            "access_key": access_key,
            "keywords": keywords,
            "countries": countries,
            "date": f"{start_date},{end_date}",
            "limit": limit,
            "offset": offset,
            "sort": "published_asc" # Sorting is required to ensure consistent pagination
        }
        
        try:
            print(f"Fetching page starting at offset {offset}...")
            response = requests.get(url, params=params)
            response.raise_for_status() 
            
            data = response.json()
            
            if "error" in data:
                print(f"API Error: {data['error'].get('message', 'Unknown error')}")
                break
                
            if total_articles is None and "pagination" in data:
                total_articles = data["pagination"]["total"]
                print(f"Discovered {total_articles} total articles in the database.")
                
            articles = data.get("data", [])
            if not articles:
                print("No more articles returned by API. Finished.")
                break
                
            all_articles.extend(articles)
            
            # Save progress after every page to prevent data loss on crash
            with open("bhp_news_dataset.json", "w", encoding="utf-8") as f:
                json.dump(all_articles, f, indent=4, ensure_ascii=False)
                
            print(f"Retrieved {len(articles)} items. Total collected so far: {len(all_articles)}")
            
            offset += limit
            
            if total_articles is not None and offset >= total_articles:
                print("Successfully fetched all available articles.")
                break
                
            # Rate limiting delay
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            print(f"HTTP Request failed: {e}")
            break
            
    # Convert JSON to CSV for your clustering pipeline
    if all_articles:
        df = pd.DataFrame(all_articles)
        
        # Keep only the relevant columns for BERTopic clustering
        columns_to_keep = ['title', 'description', 'published_at', 'source', 'url']
        available_columns = [col for col in columns_to_keep if col in df.columns]
        
        df = df[available_columns]
        df.to_csv("bhp_news_dataset.csv", index=False, encoding='utf-8')
        print("Successfully converted data and saved to bhp_news_dataset.csv")

if __name__ == "__main__":
    API_KEY = "57af11a92241514c5ec413f12836e075"
    fetch_mediastack_news_to_csv(API_KEY)