import requests
import openai
import re

def get_news_articles(api_key, query, n_articles):
    url = f"https://gnews.io/api/v4/search?q={query}&max={n_articles}&token={api_key}"
    response = requests.get(url)
    data = response.json()

    titles = []

    if response.status_code == 200 :
        articles = data.get("articles", [])
        for article in articles:
            titles.append(article.get("title"))
            print(f"Title: {titles[-1]}")
            print("--------------")
    else:
        print("Failed to retrieve news articles.")

    return titles

# Set your GNews API key
gnews_api_key = "7f087357cb888449678cb5ab68d14bb9"

# Specify the query term for articles (e.g., "artificial intelligence")
query = "artificial intelligence"

# Call the function to fetch news articles
titles = get_news_articles(gnews_api_key, query, 3)

openai_api_key = "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"

# Set up your OpenAI API credentials
openai.api_key = openai_api_key

def get_completion(prompt, model="gpt-3.5-turbo"):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0.7, 
        max_tokens=1000
    )
    return response.choices[0].message["content"]
responses = []
for title in titles:
  responses.append(get_completion(f"Write a parody of this news headline '{title}' in the style of The Daily Mash, with any proper names changed to humourous ones. Make the article no more than 200 words long. Include Markdown formatting for jekyll."))

def write_markdown_file(file_path, content):
    with open(file_path, 'w') as f:
        f.write(content)

def clean_filename(filename):
    # Remove illegal characters
    cleaned = re.sub(r'[\\/:"*?<>|]', '', filename)
    
    # Replace spaces with underscores
    cleaned = cleaned.replace(' ', '_')
    
    # Normalize case (lowercase)
    cleaned = cleaned.lower()
    
    # Limit length (optional)
    cleaned = cleaned[:255]  # Limit to 255 characters (adjust as needed)
    
    return cleaned

for title, response in zip(titles, responses):
    write_markdown_file(f"articles/{clean_filename(title)}.md", response)