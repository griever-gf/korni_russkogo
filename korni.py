import re
import pymorphy2
import gspread
from oauth2client.service_account import ServiceAccountCredentials
#import config
import os
import json
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler
import logging

PORT = int(os.environ.get('PORT', 5000))

def start_message(update):
    update.message.text('Привет, проверка связи 2')

#Let's analyze all the incoming text
def process_text(update, context):
    morph = pymorphy2.MorphAnalyzer()

    # define the scope
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

    # add credentials to the account
    #creds = ServiceAccountCredentials.from_json_keyfile_name('Korni russkogo-3d1949b6c88b.json', scope)
    json_creds = os.getenv("GOOGLE_SHEETS_CREDS_JSON")
    creds_dict = json.loads(json_creds)
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)


    # authorize the clientsheet
    client = gspread.authorize(creds)

    # get the instance of the Spreadsheet
    sheet = client.open('Корни языка')

    # get the first sheet of the Spreadsheet
    sheet_instance = sheet.get_worksheet(0)

    # get all the records of the data
    records_data = sheet_instance.get_all_records() #list of dictionaries


    id_non_native = sheet_instance.cell(col=1,row=1).value #ключ мусорного значения
    id_native = sheet_instance.cell(col=2,row=1).value #ключ родного значения

    # opening google sheet data
    for idxx, dict1 in enumerate(records_data):
        # split cell if in consist several words using re.sub(pattern, repl, string, count=0, flags=0)
        dict_words_list = re.split("[^\w-)(]*,[^\w-)(]*", dict1[id_non_native]) #split by comma + non-word chars and brackets
        for non_native_word in dict_words_list:
            print(non_native_word)
            if re.match("[\w-]*\([\w-]*\)[\w-]*", non_native_word):
                res = re.search("\([\w-]*\)", non_native_word)
                word1 =  str.replace(non_native_word, res.group(0), "")
                word2 =  str.replace(non_native_word, res.group(0), res.group(0).strip(')('))
                print("Word 1: " + word1 + " Word 2: " + word2)
                idx = dict_words_list.index(non_native_word)
                #print(dict_words_list)
                dict_words_list.remove(non_native_word)
                dict_words_list.insert(idx, word1)
                dict_words_list.insert(idx+1, word2)
                print(dict_words_list)
        records_data[idxx][id_non_native] = ', '.join(dict_words_list)

    output_message = ""

    # let's split it by words using re.sub(pattern, repl, string, count=0, flags=0)
    # [\w] means any alphanumeric character and is equal to the character set [a-zA-Z0-9_]
    input_words_list = re.sub("[^\w-]", " ", update.message.text).split()
    # print(input_words_list)

    for checked_word in input_words_list:
        # print("Проверяем: " + checked_word)
        # print(morph.parse(checked_word)[0].lexeme)
        # morph.parse(checked_word)[0].lexeme

        checked_word_lower = checked_word.lower()

        # opening google sheet data
        for dict2 in records_data:
            # print(dict[id_non_native])
            # split cell if in consist several words using re.sub(pattern, repl, string, count=0, flags=0)
            # split by comma only (useful for words with spaces)
            dict_words_list = re.split("[^\w-]*,[^\w-]*", dict2[id_non_native]) #split by comma + non-word chars
            is_coincidence_found = False
            string_to_add = ""
            for non_native_word in dict_words_list:
                # maybe should try to normalize non_native form too or to check all the forms of non_native_word
                if (checked_word_lower == non_native_word):
                    # print("Входное: " + checked_word)
                    # print("Попробуйте: " + dict2[id_native])
                    string_to_add = "Не \"" + checked_word_lower + "\", а " + dict2[id_native] + ".\n"
                    is_coincidence_found = True
                    break
                else:
                    for normal_form in morph.normal_forms(checked_word_lower):
                        if (normal_form == non_native_word):
                            string_to_add = "Не \"" + normal_form + "\", а " + dict2[id_native] + ".\n"
                            is_coincidence_found = True
                            break
                    if (is_coincidence_found):
                        break
            if (is_coincidence_found):
                break
        #check for identical incoming words - they don't need to appear several times in response message
        if (string_to_add != ""):
            if (not (string_to_add in output_message)): #optimization (maybe)
                output_message += string_to_add

    if (output_message != ""):
        output_message += "Берегите корни русского языка..."
        update.message.reply_text(output_message)


updater = Updater(os.getenv("TG_API_KEY"))

# Get the dispatcher to register handlers
dp = updater.dispatcher

dp.add_handler(CommandHandler("start", start_message))
dp.add_handler(MessageHandler(Filters.text & (~Filters.forwarded), process_text))

updater.start_webhook(listen="0.0.0.0",
                      port=PORT,
                      url_path=os.getenv("TG_API_KEY"))
updater.bot.setWebhook('https://korni-russkogo.herokuapp.com/' + os.getenv("TG_API_KEY"))
updater.idle()
