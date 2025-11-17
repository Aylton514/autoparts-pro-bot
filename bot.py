import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class AutoPartsBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        if not self.token:
            logger.error("❌ BOT_TOKEN não encontrado!")
            return
        
        self.app = Application.builder().token(self.token).build()
        self.init_database()
        self.setup_handlers()
        logger.info("🤖 AutoParts Bot inicializado com sucesso!")
    
    def init_database(self):
        """Inicializa o banco de dados simples"""
        conn = sqlite3.connect('autoparts.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price DECIMAL(10,2),
                location TEXT,
                brand TEXT
            )
        ''')
        
        # Dados de exemplo
        sample_parts = [
            ('Filtro de Óleo Toyota', 89.90, 'São Paulo, SP', 'Toyota'),
            ('Disco de Freio VW', 245.90, 'Rio de Janeiro, RJ', 'Volkswagen'),
            ('Pneu Pirelli Honda', 289.90, 'Minas Gerais, MG', 'Pirelli'),
            ('Pastilha de Freio', 45.90, 'Paraná, PR', 'Bosch'),
            ('Kit Embreagem Fiat', 420.00, 'Santa Catarina, SC', 'Luk')
        ]
        
        cursor.executemany('INSERT OR IGNORE INTO parts (name, price, location, brand) VALUES (?, ?, ?, ?)', sample_parts)
        conn.commit()
        conn.close()
    
    def setup_handlers(self):
        """Configura os handlers do bot"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("buscar", self.search_parts))
        self.app.add_handler(CommandHandler("doar", self.donate))
        self.app.add_handler(CommandHandler("ajuda", self.help_command))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        user = update.effective_user
        
        welcome_text = f"""
🔧 *Bem-vindo ao AutoParts Finder, {user.first_name}!* 🤖

*Encontre peças automotivas com facilidade:*

🚗 *Para todos os veículos:*
• Carros • Motos • Caminhões

💎 *Tipos de peças:*
✅ Originais • 🔄 Compatíveis

🔍 *Como usar:*
• /buscar <nome da peça>
• Clique nos botões abaixo
• Ou digite o nome da peça

*Exemplo:* `/buscar filtro de óleo`
"""
        
        keyboard = [
            [InlineKeyboardButton("🔍 BUSCAR PEÇAS", callback_data="search")],
            [InlineKeyboardButton("🚗 CARROS", callback_data="carros"), InlineKeyboardButton("🏍️ MOTOS", callback_data="motos")],
            [InlineKeyboardButton("💝 FAZER DOAÇÃO", callback_data="donate")],
            [InlineKeyboardButton("📞 AJUDA", callback_data="help")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def search_parts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /buscar"""
        if not context.args:
            await update.message.reply_text(
                "🔍 *Como usar:* `/buscar <nome da peça>`\n\n"
                "*Exemplos:*\n"
                "• `/buscar filtro de óleo`\n"
                "• `/buscar disco de freio`\n" 
                "• `/buscar pneu`\n"
                "• `/buscar embreagem`",
                parse_mode='Markdown'
            )
            return
        
        search_query = ' '.join(context.args)
        await self.perform_search(update, search_query)
    
    async def perform_search(self, update: Update, search_query: str):
        """Executa a busca no banco de dados"""
        search_msg = await update.message.reply_text(f"🔍 *Procurando por* `{search_query}`...", parse_mode='Markdown')
        
        conn = sqlite3.connect('autoparts.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, brand, price, location FROM parts WHERE name LIKE ? OR brand LIKE ? LIMIT 5', 
                      (f'%{search_query}%', f'%{search_query}%'))
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            await search_msg.edit_text(f"❌ *Nenhuma peça encontrada para* `{search_query}`", parse_mode='Markdown')
            return
        
        response = f"🔍 *Resultados para \"{search_query}\"*\n\n"
        response += f"*Encontrados:* {len(results)} peças\n\n"
        
        for i, part in enumerate(results, 1):
            name, brand, price, location = part
            response += f"{i}. ✅ *{name}*\n"
            response += f"   🏭 {brand} • 💰 R$ {price}\n"
            response += f"   📍 {location}\n\n"
        
        response += "💡 *Interessado em alguma peça? Entre em contato!*"
        
        keyboard = [
            [InlineKeyboardButton("🔍 NOVA BUSCA", callback_data="search")],
            [InlineKeyboardButton("💝 DOAR", callback_data="donate")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await search_msg.edit_text(response, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def donate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /doar"""
        donate_text = """
💝 *Apoie o AutoParts Finder!*

*Sua contribuição ajuda a manter:*
🤖 Servidores 24/7
🔧 Novas funcionalidades
📈 Expansão do catálogo

*Formas de contribuir:*
📧 *PayPal:* `ayltonanna@gmail.com`
💙 *Pix:* Solicite via DM

*Muito obrigado pelo apoio!* 🙏
"""
        await update.message.reply_text(donate_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ajuda"""
        help_text = """
📞 *Central de Ajuda*

*Comandos disponíveis:*
• /start - Menu principal
• /buscar - Procurar peças
• /doar - Apoiar projeto
• /ajuda - Esta mensagem

*Dicas:*
• Use termos genéricos para mais resultados
• Especifique marca/modelo para busca precisa

*Exemplos de busca:*
• `filtro de óleo toyota`
• `disco de freio gol`
• `pneu honda bros`
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manipula cliques nos botões"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "search":
            await query.edit_message_text("🔍 *Digite o nome da peça que procura:*\n\nEx: filtro, disco freio, pneu...", parse_mode='Markdown')
        elif query.data in ["carros", "motos"]:
            vehicle = "carros" if query.data == "carros" else "motos"
            await query.edit_message_text(f"🔍 *Buscar peças para {vehicle.upper()}*\n\nDigite o nome da peça:", parse_mode='Markdown')
        elif query.data == "donate":
            await self.donate(update, context)
        elif query.data == "help":
            await self.help_command(update, context)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lida com mensagens de texto normais"""
        text = update.message.text
        if text and not text.startswith('/'):
            await self.perform_search(update, text)
    
    def run(self):
        """Inicia o bot"""
        self.app.run_polling()

def main():
    bot = AutoPartsBot()
    bot.run()

if __name__ == '__main__':
    main()
