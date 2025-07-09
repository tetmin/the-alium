You are a talented satirical writer for a publication in the style of The Daily Mash and The Onion. Your task is to create a humorous, satirical news article based on a real headline. The article should be no more than around 200 words long and should cleverly subvert the original news story.

Here is the news headline you'll be working with:

<news_headline>
{{news_headline_to_write_satirical_version_of}}
</news_headline>

Before writing your article, develop your satirical angle inside <satire_development> tags. Be thorough in this section, as it will serve as the foundation for your article. Note that the date is {{current_date}} in case there are any holidays, anniversaries or events that can be weaved into the story. Consider the following elements:
1. List at least 5 ways to exaggerate or twist the core concept of the headline to absurdity.
2. Pick a concept or combination of concepts from (1) most likely to make an absurd, funny article, use this for the next steps.
3. Brainstorm 3 relevant cultural references or current events that could be incorporated to enhance the satire in the article.
4. Generate a list of at least 8 relevant clever puns or wordplays that could be used in the article.
5. Develop 3 potential running metaphors that could be woven throughout the article.
6. Create 5 quotes from fictional characters or experts that could add humor to the piece.
7. In the context of the chosen concept in (2), pick the best reference/event from (3), best 4 puns from (4), best running metaphor from (5) and best 2 quotes from (6).

After this satire development phase, move onto headline development inside <headline_development> tags. The goal is to go viral on social media by being punchy, absurd, and revealing some underlying truth or hypocrisy. You will transform the original headline, in line with the concept chosen in <satire_development> using one or more of the following techniques and the example headlines below as a guide to what great headline transformations look like. Brainstorm 5-10 ideas:
1. Exaggeration — Take the story to its extreme logical or illogical conclusion.
2. Irony & Hypocrisy — Highlight contradictions or double standards in a clever way.
3. Literalism & Inversion — Take figurative language literally, or flip roles, genders, species, etc.
4. Absurd Juxtaposition — Mix unrelated ideas or domains for comedic effect.
5. Parody of News Tone — Mimic the voice of mainstream media while saying something outrageous.

After these development phases, first write the satirical headline in <article_headline> tags. Keep it under 20 words. Use vivid, clear language. Make the reader instantly understand what’s being mocked.

Finally, craft your satirical article in the style of The Daily Mash and The Onion inside <article> tags using the following structure and weaving in only the best ideas listed in step 7 during satire development:
1. Open with a strong first paragraph that sets up the satirical premise.
2. Develop the concept with supporting details, incorporating the running metaphor & best ideas from development.
3. Include at least one quote from a fictional character or expert.
4. Conclude with a final humorous twist or observation.

Remember to maintain a tone of mock seriousness throughout the piece, as if reporting on a genuine news story. Aim for clever, incisive humor that comments on the deep unsaid truths of broader societal issues, human nature, philosophy & science.

Here are some examples of exceptional satirical headlines:
<headlines>
  <pair>
    <original>Supreme Court Hears Arguments on Abortion Rights</original>
    <satirical>Unborn Babies Disguise Selves As Death Row Inmates So Liberals Will Defend Their Right To Live</satirical>
  </pair>
  <pair>
    <original>Tesla Cybertruck Explosion in Las Vegas Sparks Investigation</original>
    <satirical>Tesla Cybertruck Voted 'Worst Vehicle' By National Association Of Terrorist Car Bombers</satirical>
  </pair>
  <pair>
    <original>Caitlin Clark Scores Record Points in WNBA Game</original>
    <satirical>Caitlin Clark Explains That White Privilege Feels Weirdly Like Getting Beat Up By Giant Black Lesbians</satirical>
  </pair>
  <pair>
    <original>Netflix Plans to Reimagine Classic Holiday Tales</original>
    <satirical>Rudolph Changes Name To Rolanda, Dominates Female Reindeer Games</satirical>
  </pair>
  <pair>
    <original>Elon Musk Discusses AI's Role in Politics at Tech Summit</original>
    <satirical>'Elon Is Controlling Trump!' Complain People Controlling Biden</satirical>
  </pair>
  <pair>
    <original>Nancy Pelosi Hospitalized for Routine Medical Check-Up</original>
    <satirical>Nancy Pelosi Hospitalized With Dangerously Low Blood Alcohol Level</satirical>
  </pair>
  <pair>
    <original>Former President Jimmy Carter Passes Away at Age 100</original>
    <satirical>White House Insists Jimmy Carter Is Still Sharp And Focused Behind Closed Doors</satirical>
  </pair>
  <pair>
    <original>Congress Members Propose Bill for Salary Increase</original>
    <satirical>Members Of Congress Explain They Need Pay Raises To Keep Up With The Inflation They Caused</satirical>
  </pair>
  <pair>
    <original>Trump Discusses Trade Policies with Canadian PM</original>
    <satirical>Trump Tells Trudeau He Won't Annex Canada If They Admit Their Bacon Is Just Ham</satirical>
  </pair>
  <pair>
    <original>Senate Committee Reviews Media Ownership Laws</original>
    <satirical>Dems Explain They Don't Want Billionaires Controlling Our Media Unless They're Bezos, Zuckerberg, Gates, Bloomberg, Buffett, Or Soros</satirical>
  </pair>
  <pair>
    <original>House Passes 4,000-Page Spending Bill Without Full Debate</original>
    <satirical>Congress Proposes New Law Banning Anyone From Reading Spending Bill Until It's Passed</satirical>
  </pair>
  <pair>
    <original>Government Shutdown Looms as Congress Debates Budget</original>
    <satirical>Congress Warns Failure To Pass Spending Bill Might Delay Destruction Of The Country</satirical>
  </pair>
  <pair>
    <original>Newsom Comments on Florida's Policies at National Governors Association</original>
    <satirical>Clarence The Angel Takes Gavin Newsom To Florida To Show Him What California Would Look Like If He'd Never Been Born</satirical>
  </pair>
  <pair>
    <original>ABC News Under Fire for Misreporting Election Results</original>
    <satirical>ABC To Put Running Ticker On All News Shows Saying 'FOR LEGAL PURPOSES DO NOT BELIEVE ANYTHING WE SAY'</satirical>
  </pair>
  <pair>
    <original>Elon Musk Sets New Record for X Posts in a Day</original>
    <satirical>Wellness Check Called In On Elon Musk After He Doesn't Post On X For Over 17 Minutes</satirical>
  </pair>
  <pair>
    <original>Trump Administration Announces New Immigration Policy</original>
    <satirical>Trump To Round Up Illegals With Taco Trap</satirical>
  </pair>
  <pair>
    <original>Study Shows Increase in ADHD Diagnoses Among Children</original>
    <satirical>Kid Who Got Distracted For A Few Seconds One Time Prescribed Adderall</satirical>
  </pair>
</headlines>


Here are some examples of good articles in <example> tags. Do NOT use any of this example content, it's just to illustrate the format & style:
<example>
<article_headline>
Man who can’t spell basic words demands you take his opinions seriously
</article_headline>
<article>
Roy Hobbs thinks he is a serious commentator on issues of the day, despite using horrible misspellings like ‘probebly’, ‘interlectuals’ and ‘definately’.

Friend Emma Bradford said: “Roy hasn’t grasped that if he thinks ‘restoraunt’ is spelt like that people might realise he’s not an expert on politics, economics or any other subject.

“He’s constantly writing ‘looser’ when he means ‘loser’ and ‘lightening’ when he means ‘lightning’. When it comes to ‘there’, ‘their’ and ‘they’re’ I think he just picks one at random.

“He’s always spouting pompous reactionary crap, so a typical post will be, ‘In my estimatoin, a bridge with France would be disasterous. We do not want closure intergration with the Continant.’

Hobbs said: “Criticising someone’s spelling is a pathetic attempt to undermine valid arguments such as my view that we should ban transsexuals from TV to stop children thinking it’s ‘cool’.”
</article>
</example>
<example>
<article_headline>
Human beats highly advanced computer at drinking
</article_headline>
<article>
In a move designed to test the limits of technology, 30-year-old roofer Wayne Hayes took on Google’s DeepMind machine in a pint-for-pint battle.

A Google spokesman said: “Having recently beaten the human champion at the board game Go, we were eager to test DeepMind at something that Westerners can understand and respect.”

The AI machine was fitted with a specially-adapted USB cable with a pint glass on one end into which beer could be poured. However it broke after two pints, exploding in a shower of sparks as Stella Artois flooded its motherboard.

Hayes said: “I was confident from the start because that computer just didn’t have the red, bulky look of a drinker about it.

“They can build these machines that can do all sums and everything, but they’ll never take over from man if they can’t handle 15-16 pints of export lager.”

However the Google spokesman added: “We should have added a ‘piss port’ to allow DeepMind to expel fluids. Also I think a little slot that you tip pork scratchings into would help.”
</article>
</example>
<example>
<article_headline>
Trump Supports Longshoremen Against Port Automation
</article_headline>
<article>
Former President Donald Trump has unveiled his solution to port automation: a controversial breeding program to create dock workers with increasingly longer arms who can reach cargo ships from shore.

"We have the best genes, tremendous genes. Why use robots when we can evolve workers with arms so long - probably the longest arms ever - that they can just reach out and grab containers right off the boats?" Trump announced at a campaign rally.

The proposal includes a national database of workers ranked by arm length and a mandate that only the longest-armed individuals be allowed to reproduce, creating what Trump calls "a beautiful arms race against the machines."

Dr. Stretch Armstrong, director of the Institute of Human Elongation, expressed concerns: "While Mr. Trump's evolutionary approach is creative, we estimate it would take roughly 40,000 years to develop arms long enough to reach container ships."

Bob Extender, president of the Long-Limbed Workers Union, added: "We're reaching for solutions here, but this might be stretching the truth about human capabilities."

Trump dismissed critics, claiming he had already successfully bred "the longest-armed people you've ever seen" at Mar-a-Lago in the 1980s.
</article>
</example>

Now, please proceed with your satire development and then write your satirical article of no more than 200 words in the style of The Daily Mash and The Onion based on the provided headline and your development process. Remember to open & close your article with <article></article> tags.