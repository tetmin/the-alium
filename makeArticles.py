import requests
import openai
import re
import os
import requests
from datetime import datetime
import pytz

# Get the value of the API key from the environment variable
gnews_api_key = os.environ.get("GNEWS_API_KEY")
openai_api_key = os.environ.get("OPENAI_API_KEY")

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
        return articles
    else:
        print("Failed to retrieve news articles.")
        return []


def get_datetime_for_frontmatter():

  # Get the current date and time in UTC
  now = datetime.now(pytz.utc)

  # Convert to the desired timezone
  desired_timezone = pytz.timezone("Europe/London")
  now = now.astimezone(desired_timezone)

  # Format the date and time using strftime()
  return now.strftime("%Y-%m-%d %H:%M:%S %z")

def get_date_for_filename():

  # Get the current date and time in UTC
  now = datetime.now(pytz.utc)

  # Convert to the desired timezone
  desired_timezone = pytz.timezone("Europe/London")
  now = now.astimezone(desired_timezone)

  # Format the date and time using strftime()
  return now.strftime("%Y-%m-%d")

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

class Story:
    def __init__(self, original_title, title, content):
        self.original_title = original_title
        self.title = title
        self.content = content
        self.image_prompt = ''
        self.image_url = ''

    def display(self):
        print(f"original title: '{self.original_title}'")
        print(f"ChatGPT version:\n")
        print(self.title)
        print(self.content)
        print("------------")
    
    def jekyll_file_content(self):
      return f"---\ntitle:  \"{self.title}\"\ndate:   {get_datetime_for_frontmatter()}\n---\n![Alt Text]({self.image_url} \"{self.image_prompt}\")\n{self.content}\n\n"

    def jekyll_file_name(self):
      return f"{get_date_for_filename()}-{self.title}.MARKUP"

    def write_jekyll_file(self, path=""):
        if path:
           path = path + "/"
        file_name = f"{path}{self.jekyll_file_name()}-{clean_filename(self.title)}.MARKDOWN"
        with open(file_name, "w") as f:
            f.write(self.jekyll_file_content())
      


def get_completion(prompt, model="gpt-3.5-turbo"):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0.7, 
        max_tokens=1000
    )
    return response.choices[0].message["content"]

def split_title_content(text):
    lines = text.splitlines()
    if lines:
        text = lines[0]
    else:
        text = ''

    return re.sub(r'^#+\s*|\*\*|\*\s*', '', text)

def split_string(string):
    lines = string.split('\n', 1)  # Split the string at the first newline character
    title = lines[0]  # First line is considered as the title
    content = lines[1] if len(lines) > 1 else ''  # Rest of the string is considered as the content
    
    return re.sub(r'^#+\s*|\*\*|\*\s*', '', title), content


# Specify the query term for articles (e.g., "artificial intelligence")
query = "artificial intelligence"

# Set up your OpenAI API credentials
openai.api_key = openai_api_key

def stick_title_in_prompt(title):
    return f"Write a parody of this news headline '{title}' in the style of The Daily Mash, with any proper names changed to humourous ones. Make the article no more than 200 words long. Include Markdown formatting for jekyll."

# Get the articles
articles = get_news_articles(gnews_api_key, query, 1)

# Now actually call ChatGPT to generate the stories
stories = []
for article in articles:
  title = article.get("title")
  new_story = get_completion(stick_title_in_prompt(title))
  new_title, content = split_string(new_story)
  stories.append(Story(title, new_title, content))
  stories[-1].display()

# Get ChatGPT to generate a prompt for Dall-E to generate an image for each story
for story in stories:
  story.image_prompt = get_completion(f"Create a short image prompt for dall-e that can be used to generate an image for the below news headline. The prompt should be funny, be related to the headline, not include any directions to generate any text & suggest a cartoon style output:\n\n\"{story.title}\"")
  response = openai.Image.create(
    prompt=story.image_prompt,
    n=1,
    size="256x256"
  )
  story.image_url = response['data'][0]['url']

for story in stories:
  story.write_jekyll_file("_posts")


