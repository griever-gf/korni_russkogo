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
        lines = open("data/answers.txt", "r", encoding="utf-8").readlines()
        lines_ex = open("data/answers_extra.txt", "r", encoding="utf-8").readlines()
        rnd_val = random.randint(1, len(lines))
        rnd_extra = random.randint(1, len(lines_ex))
        if (update.message.from_user.username == 'Tatsuya_S') and (update.message.chat.type != 'private'):
            if '#' in lines_ex[rnd_extra]:
                lines_ex[rnd_extra] = lines_ex[rnd_extra].replace("#", update.message.from_user.first_name if random.randint(1, 2) == 1 else "@" + update.message.from_user.username)
            output_message += lines_ex[rnd_extra]
        elif update.message.chat.type == 'private':
            output_message += lines[0]
        else:
            if '#' in lines[rnd_val]:
                lines[rnd_val] = lines[rnd_val].replace("#", update.message.from_user.first_name if random.randint(1, 2) == 1 else "@" + update.message.from_user.username)
            output_message += lines[rnd_val]
        update.message.reply_text(output_message)
    elif update.message.chat.type == 'private':
        output_message = "Языковая дружина проверила ваши письмена и не нашла ничего зазорного. Ладный русский слог, иностранщина не обнаружена, отпускаем вас."
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
