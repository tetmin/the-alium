import modal
import requests
import openai
import os
import re

# Setup the Modal Labs image
image = modal.Image.debian_slim().poetry_install_from_file("pyproject.toml")
stub = modal.Stub(name="dAIly-mash", image=image)


# Get some topical news article headlines
def get_news_articles(api_key, query, n_articles):
    url = f"https://gnews.io/api/v4/search?q={query}&max={n_articles}&token={api_key}"
    response = requests.get(url)
    data = response.json()

    titles = []

    if response.status_code == 200:
        articles = data.get("articles", [])
        for article in articles:
            titles.append(article.get("title"))
            print(f"Title: {titles[-1]}")
            print("--------------")
    else:
        print("Failed to retrieve news articles.")

    return titles


# OpenAI completion boilerplate
def get_completion(prompt, model="gpt-3.5-turbo"):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model, messages=messages, temperature=0.7, max_tokens=1000
    )
    return response.choices[0].message["content"]


# Clean up a filename for Jekyll
def clean_filename(filename):
    # Remove illegal characters
    cleaned = re.sub(r'[\\/:"*?<>|]', "", filename)
    # Replace spaces with underscores
    cleaned = cleaned.replace(" ", "_")
    # Normalize case (lowercase)
    cleaned = cleaned.lower()
    # Limit length (optional)
    cleaned = cleaned[:255]  # Limit to 255 characters (adjust as needed)

    return cleaned


# Generate an article from a news article title
def generate_article_from_title(title):
    prompt = f"""Write a parody of this news headline: ' {title} ' in the style of The Daily Mash, with any proper names changed to humourous ones. 
    Make the article no more than 200 words long. Include Markdown formatting for jekyll."""

    content = get_completion(prompt)
    return content


@stub.function(
    secrets=[
        modal.Secret.from_name("mark-openai-secret"),
        modal.Secret.from_name("mark-gnews-secret"),
    ]
)
def generate_posts(query, n_articles):
    titles = get_news_articles(os.environ["GNEWS_API_KEY"], query, n_articles)

    articles = [generate_article_from_title(title) for title in titles]
    filenames = [clean_filename(title) for title in titles]

    posts = zip(filenames, articles)

    return posts


# Specify the query filter for articles (e.g., "artificial intelligence")
query = "artificial intelligence"


@stub.local_entrypoint()
def main():
    posts = generate_posts.call(query, 1)

    # write each post to a file
    for filename, content in posts:
        with open(f"_posts/{filename}.md", "w") as f:
            f.write(content)


@stub.function(schedule=modal.Period(hours=5))
def scheduled():
    posts = generate_posts.call(query, 1)
