import pysrt
from pysrt import SubRipFile
from pysrt import SubRipItem

def dedup(subtitle_file):
    out = SubRipFile()
    subs = pysrt.open(subtitle_file)
    
    start = 0
    end = 0
    text = ""
    for sub in subs:
        if text != sub.text:
            item = SubRipItem(0, start, end, text)
            out.append(item)
            start = sub.start
            end = sub.end
            text = sub.text
        else:
            end = sub.end
    # last item
    item = SubRipItem(0, start, end, text)
    out.append(item)
    out.clean_indexes()
    return out

output = dedup("preface1.srt")
output.save("dedup.srt")