import os
import telebot
from flask import Flask
import threading

# Use o token fornecido (NUNCA exponha em código público!)
TOKEN = "7837160744:AAEBcXrT_xpgmw_a0qVGja6GT7FOOxhGeys"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Exemplo de comando simples
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Olá, seu bot está rodando no Render!")

# Thread para rodar o bot
def run_bot():
    print("Iniciando o bot...")
    bot.infinity_polling()

# Rota básica para manter o Flask vivo (Render precisa disso)
@app.route("/")
def index():
    return "Bot de Telegram rodando com Flask no Render!"

if __name__ == "__main__":
    # Inicia o bot em uma thread separada
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()

    # Pega a porta do ambiente (Render define a PORT)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
