import os
import logging
import sqlite3
import requests
import base64
import io
from PIL import Image
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from telegram.constants import ParseMode

# Configuração de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados da conversação
CHOOSING_LANGUAGE, SEARCHING, UPLOADING_PHOTO, DESCRIBING_PART = range(4)

class AutoPartsProBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        self.admin_id = os.getenv('ADMIN_USER_ID')
        
        if not self.token:
            raise ValueError("BOT_TOKEN não encontrado!")
        
        self.app = Application.builder().token(self.token).build()
        self.setup_handlers()
        self.init_database()
        logger.info("🤖 AutoParts Pro Bot inicializado!")
    
    def init_database(self):
        """Inicializa o banco de dados com estrutura completa"""
        conn = sqlite3.connect('autoparts_pro.db')
        cursor = conn.cursor()
        
        # Tabela de usuários
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'portugues',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de peças com fotos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_pt TEXT,
                name_en TEXT,
                name_es TEXT,
                category_pt TEXT,
                category_en TEXT,
                category_es TEXT,
                vehicle_type TEXT,
                compatible_models TEXT,
                condition TEXT,
                brand TEXT,
                price DECIMAL(10,2),
                location TEXT,
                supplier_name TEXT,
                rating DECIMAL(3,2),
                description_pt TEXT,
                description_en TEXT,
                description_es TEXT,
                image_url TEXT,
                image_base64 TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabela de buscas por imagem
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS image_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                image_base64 TEXT,
                search_results TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Inserir dados de exemplo com múltiplos idiomas
        sample_parts = [
            # Filtro de Óleo - Toyota
            (
                'Filtro de Óleo Original Toyota', 'Original Toyota Oil Filter', 'Filtro de Aceite Original Toyota',
                'Filtros', 'Filters', 'Filtros', 'carro', 'Corolla 2015-2020', 'original', 'Toyota', 89.90,
                'São Paulo, SP', 'AutoPeças Master', 4.8,
                'Filtro de óleo original Toyota com garantia de fábrica. Compatível com Corolla 2015-2020.',
                'Original Toyota oil filter with factory warranty. Compatible with Corolla 2015-2020.',
                'Filtro de aceite original Toyota con garantía de fábrica. Compatible con Corolla 2015-2020.',
                'https://example.com/filtro_oleo_toyota.jpg',
                None
            ),
            # Disco de Freio - Volkswagen
            (
                'Disco de Freio Dianteiro VW', 'VW Front Brake Disc', 'Disco de Freno Delantero VW',
                'Freios', 'Brakes', 'Frenos', 'carro', 'Gol, Voyage 2010-2019', 'original', 'Volkswagen', 245.90,
                'Rio de Janeiro, RJ', 'Desmanche Bom Preço', 4.7,
                'Disco de freio dianteiro original Volkswagen. Alta qualidade e durabilidade.',
                'Original Volkswagen front brake disc. High quality and durability.',
                'Disco de freno delantero original Volkswagen. Alta calidad y durabilidad.',
                'https://example.com/disco_freio_vw.jpg',
                None
            ),
            # Pneu Pirelli - Honda
            (
                'Pneu Traseiro Pirelli Motocross', 'Pirelli Rear Motocross Tire', 'Neumático Trasero Pirelli Motocross',
                'Pneus', 'Tires', 'Neumáticos', 'moto', 'Honda XRE 300, Bros 160', 'original', 'Pirelli', 289.90,
                'São Paulo, SP', 'MotoPeças SP', 4.6,
                'Pneu traseiro original Pirelli para trilha e cidade. Alta aderência em diversos terrenos.',
                'Original Pirelli rear tire for trail and city. High grip on various terrains.',
                'Neumático trasero original Pirelli para trail y ciudad. Alto agarre en diversos terrenos.',
                'https://example.com/pneu_pirelli.jpg',
                None
            )
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO parts 
            (name_pt, name_en, name_es, category_pt, category_en, category_es, 
             vehicle_type, compatible_models, condition, brand, price, location, 
             supplier_name, rating, description_pt, description_en, description_es, 
             image_url, image_base64)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_parts)
        
        conn.commit()
        conn.close()
        logger.info("✅ Database inicializado com dados multi-idiomas!")
    
    def setup_handlers(self):
        """Configura todos os handlers incluindo conversação"""
        # Conversation Handler para upload de fotos
        conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.start_photo_search, pattern="^search_photo$"),
                CommandHandler("foto", self.start_photo_search_command)
            ],
            states={
                UPLOADING_PHOTO: [
                    MessageHandler(filters.PHOTO, self.handle_photo_upload),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_photo_description)
                ],
                DESCRIBING_PART: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_part_description)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_operation)]
        )
        
        # Handlers principais
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("buscar", self.search_parts))
        self.app.add_handler(CommandHandler("idioma", self.change_language))
        self.app.add_handler(CommandHandler("doar", self.donate))
        self.app.add_handler(CommandHandler("ajuda", self.help_command))
        self.app.add_handler(CommandHandler("foto", self.start_photo_search_command))
        
        self.app.add_handler(conv_handler)
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
    
    def get_user_language(self, user_id):
        """Obtém o idioma preferido do usuário"""
        conn = sqlite3.connect('autoparts_pro.db')
        cursor = conn.cursor()
        cursor.execute('SELECT language FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 'portugues'
    
    def get_text(self, key, language):
        """Sistema de multi-idiomas"""
        texts = {
            'welcome': {
                'portugues': '🔧 *Bem-vindo ao AutoParts Pro!*',
                'english': '🔧 *Welcome to AutoParts Pro!*',
                'espanol': '🔧 *¡Bienvenido a AutoParts Pro!*'
            },
            'search_photo': {
                'portugues': '📸 *Buscar por Foto*',
                'english': '📸 *Search by Photo*', 
                'espanol': '📸 *Buscar por Foto*'
            },
            'upload_photo': {
                'portugues': '📸 Envie uma foto da peça que procura',
                'english': '📸 Send a photo of the part you need',
                'espanol': '📸 Envíe una foto de la pieza que necesita'
            },
            # Adicione mais textos aqui...
        }
        return texts.get(key, {}).get(language, texts.get(key, {}).get('portugues', key))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start com seleção de idioma"""
        user = update.effective_user
        self.register_user(user)
        
        language = self.get_user_language(user.id)
        
        welcome_text = self.get_text('welcome', language)
        full_text = f"""
{welcome_text}

*{user.first_name}*, encontre peças automotivas de forma inteligente!

🌐 *Recursos Premium:*
• 📸 Busca por foto da peça
• 🔍 Reconhecimento inteligente
• 💬 Multi-idiomas (PT/EN/ES)
• 🏪 Fornecedores verificados
• 💰 Comparação de preços

🚗 *Suporte completo para:*
• Carros • Motos • Caminhões
"""
        
        keyboard = [
            [InlineKeyboardButton("🔍 BUSCAR PEÇAS", callback_data="search_main")],
            [InlineKeyboardButton("📸 BUSCAR POR FOTO", callback_data="search_photo")],
            [InlineKeyboardButton("🌐 MUDAR IDIOMA", callback_data="change_language")],
            [
                InlineKeyboardButton("🚗 CARROS", callback_data="vehicle_car"),
                InlineKeyboardButton("🏍️ MOTOS", callback_data="vehicle_moto")
            ],
            [
                InlineKeyboardButton("💝 DOAR", callback_data="donate_main"),
                InlineKeyboardButton("📞 AJUDA", callback_data="help_main")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            full_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def start_photo_search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia busca por foto via comando"""
        return await self.start_photo_search(update, context)
    
    async def start_photo_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia o processo de busca por foto"""
        query = update.callback_query
        if query:
            await query.answer()
            user_id = query.from_user.id
        else:
            user_id = update.message.from_user.id
        
        language = self.get_user_language(user_id)
        
        text = self.get_text('upload_photo', language)
        
        if query:
            await query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        
        return UPLOADING_PHOTO
    
    async def handle_photo_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processa o upload da foto"""
        user = update.effective_user
        language = self.get_user_language(user.id)
        
        photo = update.message.photo[-1]  # Maior resolução
        photo_file = await photo.get_file()
        
        # Converter foto para base64
        photo_bytes = await photo_file.download_as_bytearray()
        image_base64 = base64.b64encode(photo_bytes).decode('utf-8')
        
        # Salvar no contexto para uso posterior
        context.user_data['photo_base64'] = image_base64
        
        # Pedir descrição da peça
        description_text = {
            'portugues': "📝 *Agora descreva a peça:*\n\n• Nome da peça\n• Marca do veículo\n• Modelo/Ano\n• Condição desejada\n\n*Exemplo:* \"Filtro de óleo para Toyota Corolla 2018, original\"",
            'english': "📝 *Now describe the part:*\n\n• Part name\n• Vehicle brand\n• Model/Year\n• Desired condition\n\n*Example:* \"Oil filter for Toyota Corolla 2018, original\"",
            'espanol': "📝 *Ahora describa la pieza:*\n\n• Nombre de la pieza\n• Marca del vehículo\n• Modelo/Año\n• Condición deseada\n\n*Ejemplo:* \"Filtro de aceite para Toyota Corolla 2018, original\""
        }
        
        await update.message.reply_text(
            description_text.get(language, description_text['portugues']),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return DESCRIBING_PART
    
    async def handle_part_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Processa a descrição da peça e faz a busca"""
        user = update.effective_user
        description = update.message.text
        language = self.get_user_language(user.id)
        
        # Salvar busca por imagem no banco
        conn = sqlite3.connect('autoparts_pro.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO image_searches (user_id, image_base64, search_results)
            VALUES (?, ?, ?)
        ''', (user.id, context.user_data.get('photo_base64'), description))
        conn.commit()
        conn.close()
        
        # Buscar peças compatíveis baseado na descrição
        results = await self.search_by_description(description, language)
        
        if results:
            response = self.format_photo_search_results(results, language)
        else:
            no_results_text = {
                'portugues': "❌ *Nenhuma peça compatível encontrada.*\n\nTente ser mais específico na descrição ou use /buscar",
                'english': "❌ *No compatible parts found.*\n\nTry to be more specific in the description or use /search",
                'espanol': "❌ *No se encontraron piezas compatibles.*\n\nIntente ser más específico en la descripción o use /buscar"
            }
            response = no_results_text.get(language, no_results_text['portugues'])
        
        keyboard = [
            [InlineKeyboardButton("🔍 NOVA BUSCA", callback_data="search_main")],
            [InlineKeyboardButton("📸 OUTRA FOTO", callback_data="search_photo")],
            [InlineKeyboardButton("🏠 INÍCIO", callback_data="back_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            response,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Limpar dados temporários
        context.user_data.clear()
        return ConversationHandler.END
    
    async def search_by_description(self, description: str, language: str):
        """Busca peças baseado na descrição do usuário"""
        conn = sqlite3.connect('autoparts_pro.db')
        cursor = conn.cursor()
        
        # Busca inteligente na descrição
        search_terms = description.lower().split()
        
        query = '''
            SELECT * FROM parts WHERE is_active = 1 AND (
        '''
        params = []
        
        for term in search_terms:
            if len(term) > 2:  # Ignorar palavras muito curtas
                query += f'''name_pt LIKE ? OR name_en LIKE ? OR name_es LIKE ? OR 
                          brand LIKE ? OR compatible_models LIKE ? OR '''
                params.extend([f'%{term}%'] * 5)
        
        query = query[:-4]  # Remove o último OR
        query += ') ORDER BY rating DESC, price ASC LIMIT 5'
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def format_photo_search_results(self, results, language):
        """Formata os resultados da busca por foto"""
        if language == 'portugues':
            response = "🔍 *Peças Encontradas pela Sua Foto:*\n\n"
        elif language == 'english':
            response = "🔍 *Parts Found by Your Photo:*\n\n"
        else:
            response = "🔍 *Piezas Encontradas por Tu Foto:*\n\n"
        
        for i, part in enumerate(results, 1):
            if language == 'portugues':
                name = part[1]  # name_pt
                category = part[4]  # category_pt
                description = part[16]  # description_pt
            elif language == 'english':
                name = part[2]  # name_en
                category = part[5]  # category_en
                description = part[17]  # description_en
            else:
                name = part[3]  # name_es
                category = part[6]  # category_es
                description = part[18]  # description_es
            
            price = part[11]
            brand = part[10]
            location = part[12]
            supplier = part[13]
            rating = part[14]
            
            condition_icon = "✅" if part[9] == 'original' else "🔄"
            
            response += f"{i}. {condition_icon} *{name}*\n"
            response += f"   🏭 {brand} • ⭐ {rating}/5\n"
            response += f"   💰 ${price} • 📍 {location}\n"
            response += f"   🏪 {supplier}\n\n"
        
        return response
    
    async def search_parts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Busca tradicional por texto"""
        user = update.effective_user
        language = self.get_user_language(user.id)
        
        if not context.args:
            help_text = {
                'portugues': "🔍 *Como usar:* `/buscar <nome da peça>`\n\n*Exemplos:*\n• `/buscar filtro de óleo`\n• `/buscar disco de freio`\n• `/buscar pneu honda`",
                'english': "🔍 *How to use:* `/search <part name>`\n\n*Examples:*\n• `/search oil filter`\n• `/search brake disc`\n• `/search honda tire`",
                'espanol': "🔍 *Cómo usar:* `/buscar <nombre de pieza>`\n\n*Ejemplos:*\n• `/buscar filtro de aceite`\n• `/buscar disco de freno`\n• `/buscar neumático honda`"
            }
            await update.message.reply_text(
                help_text.get(language, help_text['portugues']),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        search_query = ' '.join(context.args)
        await self.perform_search(update, search_query, language)
    
    async def perform_search(self, update: Update, search_query: str, language: str):
        """Executa a busca no banco de dados"""
        searching_text = {
            'portugues': f"🔍 *Procurando por* `{search_query}`...",
            'english': f"🔍 *Searching for* `{search_query}`...",
            'espanol': f"🔍 *Buscando* `{search_query}`..."
        }
        
        search_msg = await update.message.reply_text(
            searching_text.get(language, searching_text['portugues']),
            parse_mode=ParseMode.MARKDOWN
        )
        
        conn = sqlite3.connect('autoparts_pro.db')
        cursor = conn.cursor()
        
        # Busca multi-idioma
        query = '''
            SELECT * FROM parts WHERE is_active = 1 AND (
                name_pt LIKE ? OR name_en LIKE ? OR name_es LIKE ? OR 
                brand LIKE ? OR compatible_models LIKE ? OR category_pt LIKE ? OR
                category_en LIKE ? OR category_es LIKE ?
            ) ORDER BY rating DESC, price ASC LIMIT 8
        '''
        
        params = [f'%{search_query}%'] * 8
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            no_results_text = {
                'portugues': f"❌ *Nenhuma peça encontrada para* `{search_query}`",
                'english': f"❌ *No parts found for* `{search_query}`",
                'espanol': f"❌ *No se encontraron piezas para* `{search_query}`"
            }
            await search_msg.edit_text(
                no_results_text.get(language, no_results_text['portugues']),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        response = self.format_search_results(results, search_query, language)
        
        keyboard = [
            [InlineKeyboardButton("📸 BUSCAR POR FOTO", callback_data="search_photo")],
            [InlineKeyboardButton("🌐 MUDAR IDIOMA", callback_data="change_language")],
            [InlineKeyboardButton("🔍 NOVA BUSCA", callback_data="search_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await search_msg.edit_text(
            response,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    def format_search_results(self, results, search_query, language):
        """Formata os resultados da busca"""
        if language == 'portugues':
            response = f"🔍 *Resultados para \"{search_query}\"*\n\n"
            response += f"*Encontrados:* {len(results)} peças\n\n"
        elif language == 'english':
            response = f"🔍 *Results for \"{search_query}\"*\n\n"
            response += f"*Found:* {len(results)} parts\n\n"
        else:
            response = f"🔍 *Resultados para \"{search_query}\"*\n\n"
            response += f"*Encontrados:* {len(results)} piezas\n\n"
        
        for i, part in enumerate(results, 1):
            if language == 'portugues':
                name = part[1]  # name_pt
                description = part[16]  # description_pt
            elif language == 'english':
                name = part[2]  # name_en
                description = part[17]  # description_en
            else:
                name = part[3]  # name_es
                description = part[18]  # description_es
            
            price = part[11]
            brand = part[10]
            location = part[12]
            supplier = part[13]
            rating = part[14]
            condition = part[9]
            
            condition_icon = "✅" if condition == 'original' else "🔄"
            condition_text = {
                'portugues': 'Original' if condition == 'original' else 'Compatível',
                'english': 'Original' if condition == 'original' else 'Compatible',
                'espanol': 'Original' if condition == 'original' else 'Compatible'
            }
            
            response += f"{i}. {condition_icon} *{name}*\n"
            response += f"   🏭 {brand} • ⭐ {rating}/5\n"
            response += f"   💰 ${price} • 📍 {location}\n"
            response += f"   🏪 {supplier}\n"
            response += f"   📝 {description[:80]}...\n\n"
        
        return response
    
    async def change_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Altera o idioma do bot"""
        user = update.effective_user
        
        language_text = """
🌐 *Selecione seu idioma / Select your language / Seleccione su idioma:*

Escolha uma opção abaixo:
"""
        
        keyboard = [
            [InlineKeyboardButton("🇧🇷 Português", callback_data="lang_pt")],
            [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
            [InlineKeyboardButton("🔙 Voltar", callback_data="back_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            language_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def donate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sistema de doações multi-idioma"""
        user = update.effective_user
        language = self.get_user_language(user.id)
        
        donate_texts = {
            'portugues': """
💝 *Apoie o AutoParts Pro!*

*Sua contribuição ajuda a manter:*