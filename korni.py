import re
import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pymorphy2
import config


robot = telebot.TeleBot(config.api_key)

robot.message_handler(commands=['start'])
def start_message(message):
    robot.send_message(message.chat.id, 'Привет, проверка связи')

# define the scope
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# add credentials to the account
creds = ServiceAccountCredentials.from_json_keyfile_name('Korni russkogo-3d1949b6c88b.json', scope)

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
    dict_words_list = re.split("[^\w]*,[^\w]*", dict1[id_non_native])
    for non_native_word in dict_words_list:
        if re.match(".*\(.*\).*", non_native_word):
            res = re.search("\(.*\)", non_native_word)
            word1 =  str.replace(non_native_word, res.group(0), "")
            word2 =  str.replace(non_native_word, res.group(0), res.group(0).strip(')('))
            #print("Word 1: " + word1 + " Word 2: " + word2)
            idx = dict_words_list.index(non_native_word)
            #print(dict_words_list)
            dict_words_list.remove(non_native_word)
            dict_words_list.insert(idx, word1)
            dict_words_list.insert(idx+1, word2)
            #print(dict_words_list)
    records_data[idxx][id_non_native] = ', '.join(dict_words_list)

# view the data
#records_data
#print(records_data)

morph = pymorphy2.MorphAnalyzer()

#Let's analyze all the incoming text
@robot.message_handler(content_types=['text'])
def send_text(message):
    output_message = ""

    #let's split it by words using re.sub(pattern, repl, string, count=0, flags=0)
    #[\w] means any alphanumeric character and is equal to the character set [a-zA-Z0-9_]
    input_words_list = re.sub("[^\w]", " ", message.text).split()
    #print(input_words_list)

    for checked_word in input_words_list:
        #print("Проверяем: " + checked_word)
        #if (checked_word == "бафф"):
        #    print(morph.parse(checked_word)[0].lexeme)
        #    morph.parse(checked_word)[0].lexeme

        checked_word_normal_form = morph.normal_forms(checked_word.lower())[0]

        # opening google sheet data
        for dict2 in records_data:
            #print(dict[id_non_native])
            # split cell if in consist several words using re.sub(pattern, repl, string, count=0, flags=0)
            # split by comma only (useful for words with spaces)
            dict_words_list = re.split("[^\w]*,[^\w]*", dict2[id_non_native])
            for non_native_word in dict_words_list:
                #maybe should try to normalize non_native form too or to check all the forms of non_native_word
                if ((checked_word_normal_form == non_native_word) or (checked_word == non_native_word)):
                    #print("Входное: " + checked_word)
                    #print("Попробуйте: " + dict2[id_native])
                    output_message += "Не \"" + checked_word_normal_form + "\", а " + dict2[id_native] + ".\n"
                #else:
                    #print(checked_word_normal_form + " != " + non_native_word)
                    #print(checked_word + " != " + non_native_word)
    if (output_message != ""):
        output_message += "Берегите корни русского языка..."
        robot.send_message(message.chat.id, output_message)



robot.polling()
