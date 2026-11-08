import subprocess, wave, json, sys
FF=__import__('imageio_ffmpeg').get_ffmpeg_exe()
rate=sys.argv[1] if len(sys.argv)>1 else '190'
lines=[
"피자 프랜차이즈 아홉 개 매장, 육 년의 데이터를 들여다봤습니다.",
"매출은 십칠 퍼센트 늘었습니다.",
"그런데 주문은, 오히려 줄었습니다.",
"성장을 만든 건 고객이 아니라, 가격이었습니다.",
"이익은 구 퍼센트 증가에 그쳤습니다. 주범은 인건비입니다.",
"그리고 두 매장이, 점점 뒤처지고 있습니다.",
"고객을 늘리고, 사람을 지키고, 격차를 좁혀야 합니다.",
"데이터가 말하는, 다음 성장의 조건입니다.",
]
d=[]
for i,l in enumerate(lines):
    subprocess.run(['say','-v','Yuna','-r',rate,'-o',f'vo/{i}.aiff',l],check=True)
    subprocess.run([FF,'-y','-loglevel','error','-i',f'vo/{i}.aiff','-ar','48000','-ac','1',f'vo/{i}.wav'],check=True)
    w=wave.open(f'vo/{i}.wav'); d.append(w.getnframes()/w.getframerate())
print([round(x,2) for x in d], round(sum(d),2))
json.dump({'lines':lines,'dur':d},open('vo/meta.json','w'),ensure_ascii=False)
