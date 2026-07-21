from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
import mysql.connector
import json
import pypdf
import docx
import io
import os

load_dotenv()

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '', 
    'database': 'aiquizdb'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def extract_text_from_pdf(file_stream):
    reader = pypdf.PdfReader(file_stream)
    text = ""
    for page in reader.pages:
        content = page.extract_text()
        if content: text += content + "\n"
    return text

def extract_text_from_docx(file_stream):
    doc = docx.Document(file_stream)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def generate_ai_content(content_input, difficulty):
    # Prompt amélioré pour exiger une structure HTML riche
    prompt = f"""
    Tu es un professeur expert et un ingénieur pédagogique d'élite. Basé sur le contenu fourni, génère :
    
    1. Un résumé TRÈS DÉTAILLÉ, structuré et exhaustif. 
       - Utilise OBLIGATOIREMENT des balises HTML (<h3>, <ul>, <li>, <strong>, <br>) pour formater le texte de manière visuelle et hiérarchisée.
       - Ne saute aucune information cruciale, explique les concepts clés avec clarté.
       
    2. Un quiz de 10 questions à choix multiples de niveau '{difficulty}'. 
       - Les questions doivent être analytiques, spécifiques, et tester la véritable compréhension, pas seulement la mémorisation.
       - Les options doivent être plausibles.
    
    Tu dois obligatoirement répondre avec un objet JSON valide ayant cette structure exacte :
    {{
      "resume": "Ton résumé formaté en HTML ici...",
      "quiz": [
        {{
          "question": "La question ?",
          "options": ["Option A", "Option B", "Option C", "Option D"],
          "reponse_correcte": "La réponse correcte (doit correspondre exactement à l'une des options)",
          "explication": "Explication détaillée de la bonne réponse."
        }}
      ]
    }}
    """
    messages = [{"role": "user", "content": f"{prompt}\n\nContenu de l'étudiant :\n{content_input}"}]
    
    # Modèle plus puissant pour un meilleur rendement
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile", 
        messages=messages,
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    difficulty = request.form.get('difficulty')
    text_input = request.form.get('text_input')
    file = request.files.get('file_input')
    action = request.form.get('action', 'both') 
    
    topic = "Texte saisi"
    ai_content_input = None
    
    if file and file.filename != '':
        topic = file.filename
        filename_lower = file.filename.lower()
        file_stream = io.BytesIO(file.read())
        try:
            if filename_lower.endswith('.pdf'):
                ai_content_input = extract_text_from_pdf(file_stream)
            elif filename_lower.endswith('.docx'):
                ai_content_input = extract_text_from_docx(file_stream)
            elif filename_lower.endswith(('.png', '.jpg', '.jpeg', '.webp', '.jfif')):
                return "L'API gratuite gère les formats textuels. Veuillez convertir votre image en PDF ou copier son texte."
            elif filename_lower.endswith('.txt'):
                ai_content_input = file_stream.read().decode('utf-8')
            else:
                return "Format non supporté."
        except Exception as e:
            return f"Erreur de lecture : {str(e)}"
    else:
        if not text_input or not text_input.strip():
            return "Veuillez fournir un texte ou un fichier."
        ai_content_input = text_input
        topic = text_input[:40] + "..."

    if ai_content_input and len(ai_content_input) > 12000:
        ai_content_input = ai_content_input[:12000] + "\n\n[... Texte coupé pour la version gratuite ...]"

    try:
        ai_data = generate_ai_content(ai_content_input, difficulty)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO quiz_history (topic, difficulty, summary) VALUES (%s, %s, %s)"
        cursor.execute(sql, (topic, difficulty, ai_data['resume']))
        quiz_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()
        
        return render_template('result.html', data=ai_data, quiz_id=quiz_id, action=action)
        
    except Exception as e:
        return f"Erreur : {str(e)}"

@app.route('/save_score', methods=['POST'])
def save_score():
    data = request.get_json()
    quiz_id = data.get('quiz_id')
    score = data.get('score')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE quiz_history SET score = %s WHERE id = %s", (score, quiz_id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(debug=True)