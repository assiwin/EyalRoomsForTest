import asyncio,json
from pathlib import Path
import edge_tts
SCENES=[
'מאות תלמידים. רמות לימוד שונות. התאמות, מורים וחדרים. איך הופכים את כל זה ליום בחינה מסודר?',
'הכירו את סדרן חדרים. סביבת עבודה אחת, שמלווה אתכם מהנתונים ועד לתוצרים המוכנים.',
'טוענים את קובצי האקסל, בוחרים שכבה, ומגדירים את תנאי הבחינה. הנתונים נשארים במחשב שלכם.',
'האפליקציה מחשבת שיבוץ לפי הכללים שהוגדרו, עם התייחסות לחדרים מיוחדים ולהתאמות. התוצאה מוצגת במטריצה ברורה של מורים וחדרים.',
'צריכים לשנות את מספר החדרים? אפשר לחשב מחדש, לאזן את השיבוץ, ולבחון את התוצאה לפני שממשיכים.',
'ממפים את החדרים הפיזיים, ומפיקים דוחות למורים, דפי מעטפות, רשימת הקראה וסידורי ישיבה. קבצים מסודרים, שמוכנים להדפסה ולחלוקה.',
'לרכז הבחינות יש תמונה ברורה. למורים יש מידע מסודר. ולכל תלמיד, מקום מוגדר.',
'סדרן חדרים. יותר סדר בהכנה, יותר שליטה ביום הבחינה. רוצים לראות איך זה עובד אצלכם? בקשו הדגמה.'
]
async def main():
 p=Path('marketing/capture');(p/'narration.json').write_text(json.dumps(SCENES,ensure_ascii=False,indent=2),encoding='utf-8')
 for i,text in enumerate(SCENES):
  try:
   await asyncio.wait_for(edge_tts.Communicate(text,'he-IL-HilaNeural',rate='+3%').save(str(p/f'voice-{i}.mp3')),timeout=40)
   print('VOICE',i,'OK')
  except Exception as e: print('VOICE',i,'UNAVAILABLE',str(e))
asyncio.run(main())
