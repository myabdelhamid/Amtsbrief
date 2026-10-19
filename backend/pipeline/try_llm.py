from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client()

with open("/Users/marwannelsayed/Desktop/M/Projects/Amtsbrief/evals/data/fi_01.jpg", "rb") as f:
    bytes = f.read()

print(len(bytes))

image_part = types.Part.from_bytes(data=bytes, mime_type="image/jpeg")

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=["""
    You're given a document, I want you to follow the instructions. Follow these rules exactly:
    1. Transcribe the letter exactly as written, in German, with no translation
    2. Give one output per line of text in the letter
    3. Each output must start with L1:, L2: and so on
    4. No corrections, no summaries, no extra text before or after
    5. If a line is empty, don't output it
    
    Here is an examples of a text how your output should look like between delimiters (3 backticks):
    
    ```
    Example 1:
    Input:
    Berlin, den 17. Oktober 2026
    
    Lieber Thomas,
    
    wie geht es dir? mir geht es sehr gut.
    Ich schreibe dir, weil ich bald Geburtstag habe. Ich möchte meinen
    Geburtstg am nächsten samstag mit ein paar Freunden feiern. Die Party
    findet bei mir zu Hause statt und beginnt um 19:00 Uhr.
    Hast du Zeit und Lust zu kommen? Sag mir bitte Bescheid, ob du da sein
    kannst. Wenn du magst, kannst du auch einen Sala oder etwas zum
    Knabbern mitbringen.
    
    Ich würde mich sehr freuen dich bald wiederzusehen!
    
    Viele Grüße
    Dein Marwan Abdelhamid
              
    //////////////////////////////////////////////////
       
    Output:
    L1: Berlin, den 17. Oktober 2026
    L2: Lieber Thomas,
    L3: wie geht es dir? mir geht es sehr gut.
    L4: Ich schreibe dir, weil ich bald Geburtstag habe. Ich möchte meinen
    L5: Geburtstg am nächsten samstag mit ein paar Freunden feiern. Die Party
    L6: findet bei mir zu Hause statt und beginnt um 19:00 Uhr.
    L7: Hast du Zeit und Lust zu kommen? Sag mir bitte Bescheid, ob du da sein
    L8: kannst. Wenn du magst, kannst du auch einen Sala oder etwas zum
    L9: Knabbern mitbringen.
    L10: Ich würde mich sehr freuen dich bald wiederzusehen!
    L11: Viele Grüße
    L12: Dein Marwan Abdelhamid
    ```       
    
"""
, image_part]
)

print(response.text)

