import modal
import requests
import openai
import os
import re
from datetime import datetime
import pytz
import base64
import json
import cloudinary.uploader

# Setup the Modal Labs image
image = modal.Image.debian_slim().poetry_install_from_file("pyproject.toml")
stub = modal.Stub(name="dAIly-mash", image=image)


@stub.function(secret=modal.Secret.from_name("toms-github-secret"))
def commit_new_blog_post(filename, content):
    # GitHub repository details
    owner = "tetmin"
    repo = "dAIly-mash"
    path = f"_posts/{filename}.md"
    token = os.environ["GITHUB_TOKEN"]

    # GitHub API URL for this repository
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    # Your GitHub Personal Access Token
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Prepare the data for the API request
    data = {
        "message": "Create a new post",
        "content": base64.b64encode(
            content.encode()
        ).decode(),  # GitHub API requires the file content to be base64 encoded
        "branch": "main",
    }

    # Make the API request
    response = requests.put(url, headers=headers, data=json.dumps(data))

    # Check the response
    if response.status_code == 201:
        print("New blog post created successfully.")
    else:
        print("Failed to create new blog post. Response:", response.content)


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


class Story:
    def __init__(self, original_title, title, content):
        self.original_title = original_title
        self.title = title
        self.content = content
        self.image_prompt = ""
        self.image_url = ""

    def display(self):
        print(f"original title: '{self.original_title}'")
        print(f"ChatGPT version:\n")
        print(self.title)
        print(self.content)
        print("------------")

    def jekyll_file_content(self):
        return f'---\ntitle:  "{self.title}"\ndate:   {get_datetime_for_frontmatter()}\n---\n![Alt Text]({self.image_url} "{self.image_prompt}")\n{self.content}\n\n'

    def jekyll_file_name(self):
        return f"{get_date_for_filename()}-{clean_filename(self.original_title)}.MARKDOWN"

    def write_jekyll_file(self, path=""):
        if path:
            path = path + "/"
        file_name = f"{path}{self.jekyll_file_name()}"
        with open(file_name, "w") as f:
            f.write(self.jekyll_file_content())


def get_completion(prompt, model="gpt-3.5-turbo"):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model, messages=messages, temperature=0.7, max_tokens=1000
    )
    return response.choices[0].message["content"]


def split_string(string):
    lines = string.split("\n", 1)  # Split the string at the first newline character
    title = lines[0]  # First line is considered as the title
    content = (
        lines[1] if len(lines) > 1 else ""
    )  # Rest of the string is considered as the content

    return re.sub(r"^#+\s*|\*\*|\*\s*", "", title), content

def get_existing_titles():
    # Send the GET request
    response = requests.get("https://api.github.com/repos/tetmin/dAIly-mash/contents/_posts")

    names = []
    # If the request was successful, the status code will be 200
    if response.status_code == 200:
        # Load the JSON data from the response
        data = json.loads(response.text)
        
        # Print the name of each file in the directory
        for file in data:
            names.append(file["name"][11:-9])
            print(names[-1])
            
    else:
        print(f"Request failed with status code {response.status_code}")

    return names

def b_new_story(title):
    """ Check to make sure we haven't done this story already. """
    # Get index of story titles already in repo
    existing_titles = get_existing_titles()
    
    # return match result
    return clean_filename(title) not in existing_titles

@stub.function(
    secrets=[
        modal.Secret.from_name("mark-openai-secret"),
        modal.Secret.from_name("mark-gnews-secret"),
        modal.Secret.from_name("toms-cloudinary-secret"),
    ]
)
def generate_posts(query, n_articles):
    # Get the articles
    articles = get_news_articles(os.environ["GNEWS_API_KEY"], query, n_articles)

    # Now actually call ChatGPT to generate the stories
    stories = []
    for article in articles:
        title = article.get("title")
        if b_new_story(title):
            new_story = get_completion(stick_title_in_prompt(title))
            new_title, content = split_string(new_story)
            stories.append(Story(title, new_title, content))
            stories[-1].display()

    # Get ChatGPT to generate a prompt for Dall-E to generate an image for each story
    for story in stories:
        story.image_prompt = get_completion(
            f"""Briefly describe an image which go along with the below headline in a satirical news article. The image should be funny or ironic. 
            Use no more than 50 words. Don't try to include signs, text or logos in the image:\n\n"{story.title}"""
        )
        response = openai.Image.create(prompt=story.image_prompt, n=1, size="512x512")
        story.image_url = response["data"][0]["url"]
        response = cloudinary.uploader.upload(story.image_url)
        story.image_url = response["secure_url"]

    return stories


# Specify the query filter for articles (e.g., "artificial intelligence")
query = "artificial intelligence"


# Specify the prompt for generating the satirical article
def stick_title_in_prompt(title):
    return f"""You are a staff writer at The Daily Mash. Write a parody of the provided original news headline in the style of The Daily Mash. 
    Ensure any proper names changed to humorous ones as the Daily Mash usually does. Make the article no more than 200 words long. 
    Include Markdown formatting for Jekyll. Below are some examples of Daily Mash style articles to give you an idea of the style.\n\n

    Article Example:\n
    # Man who can’t spell basic words demands you take his opinions seriously\n
    Roy Hobbs thinks he is a serious commentator on issues of the day, despite using horrible misspellings like ‘probebly’, ‘interlectuals’ and ‘definately’.\n\n
    Friend Emma Bradford said: “Roy hasn’t grasped that if he thinks ‘restoraunt’ is spelt like that people might realise he’s not an expert on politics, economics or any other subject.\n\n
    “He’s constantly writing ‘looser’ when he means ‘loser’ and ‘lightening’ when he means ‘lightning’. When it comes to ‘there’, ‘their’ and ‘they’re’ I think he just picks one at random.\n\n
    “He’s always spouting pompous reactionary crap, so a typical post will be, ‘In my estimatoin, a bridge with France would be disasterous. We do not want closure intergration with the Continant.’\n\n
    Hobbs said: “Criticising someone’s spelling is a pathetic attempt to undermine valid arguments such as my view that we should ban transsexuals from TV to stop children thinking it’s ‘cool’.”\n\n

    Article Example:\n
    # Human beats highly advanced computer at drinking\n
    In a move designed to test the limits of technology, 30-year-old roofer Wayne Hayes took on Google’s DeepMind machine in a pint-for-pint battle.\n\n
    A Google spokesman said: “Having recently beaten the human champion at the board game Go, we were eager to test DeepMind at something that Westerners can understand and respect.”\n\n
    The AI machine was fitted with a specially-adapted USB cable with a pint glass on one end into which beer could be poured. 
    However it broke after two pints, exploding in a shower of sparks as Stella Artois flooded its motherboard.\n\n
    Hayes said: “I was confident from the start because that computer just didn’t have the red, bulky look of a drinker about it.\n\n
    “They can build these machines that can do all sums and everything, but they’ll never take over from man if they can’t handle 15-16 pints of export lager.”\n\n
    However the Google spokesman added: “We should have added a ‘piss port’ to allow DeepMind to expel fluids. Also I think a little slot that you tip pork scratchings into would help.”\n\n

    Original  News Headline: {title}
    """


@stub.local_entrypoint()
def main():
    stories = generate_posts.call(query, 1)

    # Write the stories to disk
    for story in stories:
        story.write_jekyll_file("_posts")


@stub.function(schedule=modal.Period(hours=5))
def scheduled():
    stories = generate_posts.call(query, 1)

    # commit each post to GitHub
    for story in stories:
        commit_new_blog_post.call(story.jekyll_file_name(), story.jekyll_file_content())
