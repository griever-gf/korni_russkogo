import re
import pymorphy2
import psycopg2
import os
import sys
import random
import urllib.parse as urlparse
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
try:
    import config
except ModuleNotFoundError:
    # if no config (i.e. prod)
    pass

PORT = int(os.environ.get('PORT', 5000))
morph = pymorphy2.MorphAnalyzer()


def message_how(update, context):
    # Send a message when the command /start is issued.
    update.message.reply_text('Способы использования:\nНаилучший способ - добавить (ро)бота к себе в болталки (беседы),'
                            ' тогда он будет поправлять всех участников. Для "супергрупп" нужны права заведующего.'
                            '\n\nУпрощённый способ - просто присылать любые письмена боту в личку, он тоже будет'
                            ' их поправлять. Но придётся каждый раз вручную это делать.')

def message_info(update, context):
    # Send a message when the command /start is issued.
    update.message.reply_text('Дополнительные сведения можно изведать по ссылке:\n'
                            'https://telegra.ph/Robot-popravlyalshchik-dlya-Telegrama-Korni-russkogo-04-10')


# Let's analyze all the incoming text
def process_text(update, context):
    # connect to database
    try:
        if 'DATABASE_URL' in os.environ:  # if prod
            url = urlparse.urlparse(os.environ['DATABASE_URL'])
            conn = psycopg2.connect(dbname=url.path[1:], user=url.username, password=url.password, host=url.hostname, port=url.port)
        else:
            conn = psycopg2.connect(dbname=config.db_name, user=config.db_user, password=config.db_password, host=config.db_host)
    except psycopg2.OperationalError as e:
        print('Unable to connect!\n{0}').format(e)
        sys.exit(1)
    else:
        pass
    cursor = conn.cursor()

    # get column names
    cursor.execute("SELECT column_name FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = N'rodno_data'")
    records = cursor.fetchall()
    id_non_native = records[0][0]
    id_native = records[1][0]
    id_exclusions = records[2][0]

    output_message = ""

    text_to_split = update.message.caption if (update.message.text is None) else update.message.text

    # let's split it by words using re.sub(pattern, repl, string, count=0, flags=0)
    # [\w] means any alphanumeric character and is equal to the character set [a-zA-Z0-9_]
    input_words_list = re.sub("[^\w-]", " ", text_to_split).split()

    for checked_word in input_words_list:
        checked_word_lower = checked_word.lower().removesuffix("-то").removesuffix("-ка").removesuffix("-таки").removeprefix("таки-")
        if checked_word_lower == "":
            continue

        string_to_add = ""
        cursor.execute("SELECT " + id_native + " FROM rodno_data WHERE " + id_non_native + "='" + checked_word_lower + "'")
        fix_recommendation = cursor.fetchone()
        if fix_recommendation is not None:
            string_to_add = "Не \"" + checked_word_lower + "\", а " + fix_recommendation[0] + ".\n"
        else:
            for normal_form in morph.normal_forms(checked_word_lower):
                cursor.execute("SELECT " + id_native + " FROM rodno_data WHERE " + id_non_native + "='" + normal_form + "' AND '" + checked_word_lower + "' NOT IN (SELECT * FROM unnest(\"" + id_exclusions + "\"))")
                fix_recommendation = cursor.fetchone()
                if fix_recommendation is not None:
                    string_to_add = "Не \"" + normal_form + "\", а " + fix_recommendation[0] + ".\n"
                    break
        if string_to_add != "":
            if not (string_to_add in output_message): #optimization (maybe)
                output_message += string_to_add

    cursor.close()
    conn.close()

    if output_message != "":
        output_message += "\n"
        rnd_val = random.randint(1, 6)
        if (update.message.from_user.username == 'Tatsuya_S') and (random.randint(1, 3) == 1):
            output_message += "Раз ты якобы русский, используй слова с русскими корнями, " + update.message.from_user.first_name + "."
        elif rnd_val == 1:
            output_message += "Берегите корни русского языка..."
        elif rnd_val == 2:
            output_message += "Запомни это, @" + update.message.from_user.username + ". Береги русский язык от вредного мусора."
        elif rnd_val == 3:
            output_message += "Корни русского языка заслуживают такой же охраны и любви, как древнее зодчество, редкие растения и животные."
        elif rnd_val == 4:
            output_message += "Используй НАШИ слова, @" + update.message.from_user.username + " - ведь они КРУТЫЕ, ОСОБЕННЫЕ и РОДНЫЕ."
        elif rnd_val == 5:
            output_message += "Наш особенный язык и уклад - огромное преимущество на мировом поприще и повод для полноценного самоощущения и гордости."
        elif rnd_val == 6:
            output_message += "Чуждые мусорные заимствования разъедают наш язык подобно раку. Береги и преумножай славянские корни языка, " + update.message.from_user.first_name + "."
        update.message.reply_text(output_message)


def main():
    """Start the bot."""
    updater = Updater(os.getenv("TG_API_KEY") if ('TG_API_KEY' in os.environ) else config.api_key)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('how', message_how))
    dp.add_handler(CommandHandler('info', message_info))
    dp.add_handler(MessageHandler((Filters.text | Filters.caption) & ((~Filters.forwarded) | Filters.private), process_text, pass_user_data=True))

    if ('TG_API_KEY' in os.environ):  # if prod
        updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=os.getenv("TG_API_KEY"))
        updater.bot.setWebhook('https://korni-russkogo.herokuapp.com/' + os.getenv("TG_API_KEY"))
    else: #if dev
        updater.start_polling()

    updater.idle()


if __name__ == '__main__':
    main()
