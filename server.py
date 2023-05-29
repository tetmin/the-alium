import modal
import requests
import openai
import os
import re

# Setup the Modal Labs stub
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

# Clean up the filename for Jekyll
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


# TODO: Update to add articles to the _posts directory from remote server
def write_markdown_file(file_path, content):
    with open(file_path, "w") as f:
        f.write(content)

# Generate a Jekyll post from a news article title
def generate_post_from_title(title, prompt):
    content = get_completion(prompt)
    filename = clean_filename(title)
    file_path = f"{filename}.md"
    write_markdown_file(file_path, content)


@stub.function(secrets=[modal.Secret.from_name("mark-openai-secret"),modal.Secret.from_name("mark-gnews-secret")])
def generate_posts(query, prompt, n_articles):
    titles = get_news_articles(os.environ["GNEWS_API_KEY"], query, n_articles)

    for title in titles:
        generate_post_from_title(title, prompt)


# Specify the query filter for articles (e.g., "artificial intelligence")
query = "artificial intelligence"

# Specify the prompt for generating the satirical article
prompt = f"Write a parody of this news headline in the style of The Daily Mash, with any proper names changed to humourous ones. Make the article no more than 200 words long. Include Markdown formatting for jekyll."


@stub.local_entrypoint()
def main():
    print('hellp world')
    generate_posts.call(query, prompt, 1)
