import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes, CallbackQueryHandler
)
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta  # pip install python-dateutil
import uuid

DB_NAME = 'financas.db'
(
    TIPO, VALOR, DATA, DESCRICAO,
    PARCELADO_VALOR, PARCELADO_PARCELAS, PARCELADO_DATA, PARCELADO_DESC
) = range(8)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tipo TEXT,
            valor REAL,
            data TEXT,
            descricao TEXT,
            grupo_parcela TEXT
        )
    ''')
    # Garante que a coluna grupo_parcela exista mesmo em bancos antigos
    cursor.execute("PRAGMA table_info(transacoes)")
    columns = [x[1] for x in cursor.fetchall()]
    if 'grupo_parcela' not in columns:
        cursor.execute("ALTER TABLE transacoes ADD COLUMN grupo_parcela TEXT")
    conn.commit()
    conn.close()

menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💸 Novo Gasto"), KeyboardButton("💰 Nova Receita")],
        [KeyboardButton("💳 Gasto Parcelado"), KeyboardButton("🏦 Guardar Dinheiro")],
        [KeyboardButton("📊 Saldo"), KeyboardButton("📈 Gráfico"), KeyboardButton("🗑️ Apagar Registro")]
    ],
    resize_keyboard=True
)
cancel_keyboard = ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True)

def parse_data_br(texto):
    texto = texto.strip().lower()
    if texto == "hoje":
        return datetime.today()
    try:
        # DD/MM/AAAA
        return datetime.strptime(texto, "%d/%m/%Y")
    except ValueError:
        pass
    try:
        # DD/MM (assume ano atual)
        dt = datetime.strptime(texto, "%d/%m")
        return dt.replace(year=datetime.today().year)
    except ValueError:
        pass
    try:
        # AAAA-MM-DD (compatibilidade antiga)
        return datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        pass
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Olá! O que você deseja fazer?\nEscolha uma opção abaixo:",
        reply_markup=menu_keyboard
    )

async def escolha_acao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    context.user_data.clear()
    if texto == "💸 Novo Gasto":
        context.user_data['tipo'] = "gasto"
        await update.message.reply_text("💸 Qual o valor do gasto?", reply_markup=cancel_keyboard)
        return VALOR
    elif texto == "💰 Nova Receita":
        context.user_data['tipo'] = "receita"
        await update.message.reply_text("💰 Qual o valor da receita?", reply_markup=cancel_keyboard)
        return VALOR
    elif texto == "🏦 Guardar Dinheiro":
        context.user_data['tipo'] = "guardado"
        await update.message.reply_text("🏦 Quanto você quer guardar?", reply_markup=cancel_keyboard)
        return VALOR
    elif texto == "💳 Gasto Parcelado":
        await update.message.reply_text("💳 Qual o valor total da compra?", reply_markup=cancel_keyboard)
        return PARCELADO_VALOR
    elif texto == "📊 Saldo":
        await saldo(update, context)
        return ConversationHandler.END
    elif texto == "📈 Gráfico":
        await grafico(update, context)
        return ConversationHandler.END
    elif texto == "🗑️ Apagar Registro":
        await apagar_registro(update, context)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❓ Escolha uma opção válida nos botões abaixo.", reply_markup=menu_keyboard)
        return ConversationHandler.END

async def valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancelar":
        await cancelar(update, context)
        return ConversationHandler.END
    try:
        context.user_data['valor'] = float(update.message.text.replace(",", "."))
        await update.message.reply_text("📅 Informe a data (DD/MM/AAAA, DD/MM ou 'hoje'):", reply_markup=cancel_keyboard)
        return DATA
    except ValueError:
        await update.message.reply_text("⛔ Valor inválido! Digite apenas números, por favor.", reply_markup=cancel_keyboard)
        return VALOR

async def data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancelar":
        await cancelar(update, context)
        return ConversationHandler.END
    texto = update.message.text.strip().lower()
    data_input = parse_data_br(texto)
    if not data_input:
        await update.message.reply_text("⛔ Data inválida! Use DD/MM/AAAA, DD/MM ou 'hoje'.", reply_markup=cancel_keyboard)
        return DATA
    context.user_data['data'] = data_input.strftime("%Y-%m-%d")
    await update.message.reply_text("📝 Escreva uma descrição rápida:", reply_markup=cancel_keyboard)
    return DESCRICAO

async def descricao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancelar":
        await cancelar(update, context)
        return ConversationHandler.END
    context.user_data['descricao'] = update.message.text
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute(
            "INSERT INTO transacoes (user_id, tipo, valor, data, descricao) VALUES (?, ?, ?, ?, ?)",
            (
                update.effective_user.id,
                context.user_data['tipo'],
                context.user_data['valor'],
                context.user_data['data'],
                context.user_data['descricao']
            )
        )
    tipo_emoji = {"gasto": "💸", "receita": "💰", "guardado": "🏦"}
    msg = (
        f"✅ {tipo_emoji[context.user_data['tipo']]} Registro salvo!\n"
        f"➡️ Valor: R${context.user_data['valor']:.2f}\n"
        f"📅 Data: {context.user_data['data']}\n"
        f"📝 Descrição: {context.user_data['descricao']}\n"
        f"🎉 Parabéns pela sua organização financeira!"
    )
    await update.message.reply_text(msg)
    await saldo(update, context)
    await update.message.reply_text(
        "🌟 O que deseja fazer agora?",
        reply_markup=menu_keyboard
    )
    return ConversationHandler.END

# --- GASTO PARCELADO ---
async def parcelado_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancelar":
        await cancelar(update, context)
        return ConversationHandler.END
    try:
        context.user_data['parcelado_valor'] = float(update.message.text.replace(",", "."))
        await update.message.reply_text("🔢 Em quantas parcelas?", reply_markup=cancel_keyboard)
        return PARCELADO_PARCELAS
    except ValueError:
        await update.message.reply_text("⛔ Valor inválido! Digite apenas números.", reply_markup=cancel_keyboard)
        return PARCELADO_VALOR

async def parcelado_parcelas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancelar":
        await cancelar(update, context)
        return ConversationHandler.END
    try:
        num = int(update.message.text)
        if num < 2 or num > 36:
            await update.message.reply_text("⛔ Número de parcelas deve ser entre 2 e 36.", reply_markup=cancel_keyboard)
            return PARCELADO_PARCELAS
        context.user_data['parcelado_parcelas'] = num
        await update.message.reply_text("📅 Data da 1ª parcela (DD/MM/AAAA, DD/MM ou 'hoje'):", reply_markup=cancel_keyboard)
        return PARCELADO_DATA
    except ValueError:
        await update.message.reply_text("⛔ Digite um número inteiro de parcelas.", reply_markup=cancel_keyboard)
        return PARCELADO_PARCELAS

async def parcelado_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancelar":
        await cancelar(update, context)
        return ConversationHandler.END
    texto = update.message.text.strip().lower()
    data_base = parse_data_br(texto)
    if not data_base:
        await update.message.reply_text("⛔ Data inválida! Use DD/MM/AAAA, DD/MM ou 'hoje'.", reply_markup=cancel_keyboard)
        return PARCELADO_DATA
    context.user_data['parcelado_data'] = data_base
    await update.message.reply_text("📝 Escreva uma descrição para a compra:", reply_markup=cancel_keyboard)
    return PARCELADO_DESC

async def parcelado_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Cancelar":
        await cancelar(update, context)
        return ConversationHandler.END
    descricao = update.message.text
    valor_total = context.user_data['parcelado_valor']
    num_parcelas = context.user_data['parcelado_parcelas']
    valor_parcela = round(valor_total / num_parcelas, 2)
    data_base = context.user_data['parcelado_data']
    user_id = update.effective_user.id
    grupo_id = str(uuid.uuid4())

    with sqlite3.connect(DB_NAME) as conn:
        for i in range(num_parcelas):
            data_parcela = (data_base + relativedelta(months=+i)).strftime("%Y-%m-%d")
            desc_parcela = f"{descricao} ({i+1}/{num_parcelas})"
            conn.execute(
                "INSERT INTO transacoes (user_id, tipo, valor, data, descricao, grupo_parcela) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, "gasto", valor_parcela, data_parcela, desc_parcela, grupo_id)
            )
    await update.message.reply_text(
        f"✅ {num_parcelas} parcelas de R${valor_parcela:.2f} registradas com sucesso!\n"
        f"🗓️ De {data_base.strftime('%d/%m/%Y')} até {(data_base + relativedelta(months=+(num_parcelas-1))).strftime('%d/%m/%Y')}\n"
        f"📝 Descrição: {descricao}"
    )
    await saldo(update, context)
    await update.message.reply_text(
        "🌟 O que deseja fazer agora?",
        reply_markup=menu_keyboard
    )
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operação cancelada. 😉", reply_markup=menu_keyboard)
    return ConversationHandler.END

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        uid = update.effective_user.id
        cursor.execute("SELECT SUM(valor) FROM transacoes WHERE user_id=? AND tipo='receita'", (uid,))
        receitas = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(valor) FROM transacoes WHERE user_id=? AND tipo='gasto'", (uid,))
        gastos = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(valor) FROM transacoes WHERE user_id=? AND tipo='guardado'", (uid,))
        guardado = cursor.fetchone()[0] or 0
    dispo = receitas - gastos
    total = dispo + guardado
    msg = (
        f"📊 Seu Resumo Financeiro:\n\n"
        f"💼 Saldo disponível: R${dispo:.2f}\n"
        f"🏦 Guardado: R${guardado:.2f}\n"
        f"💎 Total geral: R${total:.2f}\n\n"
        f"👍 Continue registrando seus movimentos! 🚀"
    )
    await update.message.reply_text(msg, reply_markup=menu_keyboard)

async def grafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import matplotlib.pyplot as plt
    import io
    uid = update.effective_user.id
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                strftime('%Y-%m', data) as mes,
                tipo,
                SUM(valor)
            FROM transacoes
            WHERE user_id=?
            GROUP BY mes, tipo
            ORDER BY mes ASC
            """, (uid,))
        rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("❌ Ainda não há dados para gerar o gráfico.\nRegistre alguma transação primeiro!", reply_markup=menu_keyboard)
        return
    meses = sorted(set(r[0] for r in rows if r[0]))
    dados = {m: {"receita":0, "gasto":0, "guardado":0} for m in meses}
    for mes, tipo, valor in rows:
        if mes:
            dados[mes][tipo] = valor
    receitas = [dados[m]["receita"] for m in meses]
    gastos = [dados[m]["gasto"] for m in meses]
    guardado = [dados[m]["guardado"] for m in meses]
    plt.figure(figsize=(8,5))
    plt.plot(meses, receitas, label="💰 Receitas", marker="o", color="green")
    plt.plot(meses, gastos, label="💸 Gastos", marker="o", color="red")
    plt.plot(meses, guardado, label="🏦 Guardado", marker="o", color="blue")
    plt.xlabel("Mês")
    plt.ylabel("R$ Valor")
    plt.title("📈 Evolução Financeira Mensal")
    plt.legend()
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    await update.message.reply_photo(buf, caption="📊 Seu gráfico financeiro mensal!", reply_markup=menu_keyboard)

async def apagar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Últimos registros não parcelados
        cursor.execute(
            "SELECT id, tipo, valor, data, descricao FROM transacoes WHERE user_id=? AND (grupo_parcela IS NULL OR grupo_parcela='') ORDER BY id DESC LIMIT 5",
            (uid,))
        linhas = cursor.fetchall()
        # Últimos grupos de parcelas (apenas mostra o primeiro registro de cada grupo)
        cursor.execute(
            "SELECT grupo_parcela, MIN(id), MIN(data), descricao, COUNT(*) as qtd, SUM(valor) as total FROM transacoes WHERE user_id=? AND grupo_parcela IS NOT NULL AND grupo_parcela != '' GROUP BY grupo_parcela ORDER BY MIN(id) DESC LIMIT 5",
            (uid,))
        grupos = cursor.fetchall()
    buttons = []
    if linhas:
        buttons += [
            [InlineKeyboardButton(
                f"{'💸' if tipo=='gasto' else '💰' if tipo=='receita' else '🏦'} R${valor:.2f} ({datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')}) - {descricao[:10]}",
                callback_data=f"del_{id}"
            )]
            for id, tipo, valor, data, descricao in linhas
        ]
    if grupos:
        buttons += [
            [InlineKeyboardButton(
                f"🗑️ Apagar todas parcelas: {descricao.split('(')[0].strip()} ({qtd}x R${(total/qtd):.2f})",
                callback_data=f"delgroup_{grupo_parcela}"
            )]
            for grupo_parcela, _, _, descricao, qtd, total in grupos
        ]
    if not buttons:
        await update.message.reply_text("Nenhum registro encontrado para apagar.", reply_markup=menu_keyboard)
        return
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "🗑️ Selecione um registro individual ou uma compra parcelada para apagar:",
        reply_markup=reply_markup
    )

async def apagar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("delgroup_"):
        grupo_id = query.data.replace("delgroup_", "")
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM transacoes WHERE grupo_parcela=?", (grupo_id,))
        await query.edit_message_text("✅ Todas as parcelas dessa compra foram apagadas!")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🌟 O que deseja fazer agora?",
            reply_markup=menu_keyboard
        )
    elif query.data.startswith("del_"):
        id_to_delete = int(query.data.split("_")[1])
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transacoes WHERE id=?", (id_to_delete,))
            conn.commit()
        await query.edit_message_text("✅ Registro apagado com sucesso!")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🌟 O que deseja fazer agora?",
            reply_markup=menu_keyboard
        )

def main():
    init_db()
    TOKEN = "7837160744:AAEBcXrT_xpgmw_a0qVGja6GT7FOOxhGeys"
    app = ApplicationBuilder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(
            filters.Regex(
                "^(💸 Novo Gasto|💰 Nova Receita|🏦 Guardar Dinheiro|💳 Gasto Parcelado|📊 Saldo|📈 Gráfico|🗑️ Apagar Registro)$"
            ),
            escolha_acao
        )],
        states={
            VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, valor)],
            DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, data)],
            DESCRICAO: [MessageHandler(filters.TEXT & ~filters.COMMAND, descricao)],
            PARCELADO_VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, parcelado_valor)],
            PARCELADO_PARCELAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, parcelado_parcelas)],
            PARCELADO_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, parcelado_data)],
            PARCELADO_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, parcelado_desc)],
        },
        fallbacks=[
            CommandHandler("cancelar", cancelar),
            MessageHandler(filters.Regex("^(❌ Cancelar)$"), cancelar),
        ],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(apagar_callback, pattern="^(del_|delgroup_)"))
    print("Bot rodando...")

    # Detecta ambiente Render e usa webhook
    if "RENDER_EXTERNAL_HOSTNAME" in os.environ:
        PORT = int(os.environ.get("PORT", 8443))
        HOST = os.environ["RENDER_EXTERNAL_HOSTNAME"]
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"https://{HOST}/{TOKEN}"
        )
    else:
        app.run_polling()

if __name__ == '__main__':
    main()