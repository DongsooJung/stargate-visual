# -*- coding: utf-8 -*-
# 서울 열린데이터광장 아파트 실거래 → 대시보드/지도용 집계 JSON 생성.
# 산출: assets/gu_prices.json, assets/seoul_monthly.json, assets/gu_heatmap.json
# 키는 환경변수 SEOUL_KEY 로만 전달 (코드/리포에 미포함). GitHub Actions Secret 사용.
import os, json, statistics as st, urllib.request, io, sys
from collections import defaultdict

KEY = os.environ["SEOUL_KEY"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
GEO = os.path.join(ASSETS, "seoul_gu.json")

GU = [
 ("11110","종로구"),("11140","중구"),("11170","용산구"),("11200","성동구"),("11215","광진구"),
 ("11230","동대문구"),("11260","중랑구"),("11290","성북구"),("11305","강북구"),("11320","도봉구"),
 ("11350","노원구"),("11380","은평구"),("11410","서대문구"),("11440","마포구"),("11470","양천구"),
 ("11500","강서구"),("11530","구로구"),("11545","금천구"),("11560","영등포구"),("11590","동작구"),
 ("11620","관악구"),("11650","서초구"),("11680","강남구"),("11710","송파구"),("11740","강동구"),
]

def load_years():
    """현재/전년 연도 문자열 (CI 실행 시점 기준)."""
    y = int(os.environ.get("AGG_YEAR", "0"))
    if y == 0:
        import datetime
        y = datetime.datetime.utcnow().year
    return str(y), str(y - 1)

geo = json.load(open(GEO, encoding="utf-8"))
ko2en = {f["properties"]["name"]: f["properties"]["name_eng"] for f in geo["features"]}
CUR, PREV = load_years()

def call(cgg, yr, s, e):
    url = f"http://openapi.seoul.go.kr:8088/{KEY}/json/tbLnOpendataRtmsV/{s}/{e}/{yr}/{cgg}/"
    with urllib.request.urlopen(url, timeout=40) as r:
        d = json.load(io.TextIOWrapper(r, encoding="utf-8"))
    svc = d.get("tbLnOpendataRtmsV", {})
    return svc.get("list_total_count", 0), svc.get("row", [])

def apts(cgg, yr, cap=8):
    total, _ = call(cgg, yr, 1, 1); out=[]; got=0; page=1
    while got < total and page <= cap:
        _, rows = call(cgg, yr, page*1000-999, page*1000)
        if not rows: break
        for r in rows:
            if r.get("BLDG_USG") != "아파트": continue
            try:
                amt=float(r["THING_AMT"]); area=float(r["ARCH_AREA"]); day=str(r["CTRT_DAY"])
            except (ValueError,TypeError,KeyError): continue
            if area>0 and len(day)==8:
                out.append((day[:4]+"-"+day[4:6], amt/(area/3.3058)))
        got += len(rows); page += 1
    return out

gu_prices={}; monthly=defaultdict(list); gu_month=defaultdict(lambda: defaultdict(int))
for cgg, ko in GU:
    aC=apts(cgg,CUR); aP=apts(cgg,PREV)
    en=ko2en.get(ko)
    if not en: continue
    pC=[p for _,p in aC]; pP=[p for _,p in aP]; allp=pC+pP
    if not allp: continue
    yoy = round((st.median(pC)/st.median(pP)-1)*100,1) if pP and pC else 0
    gu_prices[en]={"ko":ko,"price":round(st.median(allp)),"vol":len(pC),"yoy":yoy,"n":len(allp)}
    for m,p in aC+aP:
        monthly[m].append(p); gu_month[ko][m]+=1
    print(f"  {ko:6} price {gu_prices[en]['price']:>6,} vol {len(pC):>4} yoy {yoy}%", file=sys.stderr)

months=sorted(monthly.keys())[-18:]
seoul_monthly=[{"month":m,"volume":len(monthly[m]),"medianPyeong":round(st.median(monthly[m]))} for m in months]
top8=sorted(gu_prices.items(), key=lambda x:-x[1]["vol"])[:8]
hm_months=months[-6:]; hm_dist=[o["ko"] for _,o in top8]
z=[[gu_month[ko].get(m,0) for m in hm_months] for ko in hm_dist]

meta={"source":"서울 열린데이터광장 tbLnOpendataRtmsV (아파트 실거래)","period":f"{PREV}~{CUR} 접수분","updated_note":"월간 자동 갱신"}
def dump(name,obj): json.dump(obj, open(os.path.join(ASSETS,name),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
dump("gu_prices.json", {"meta":{**meta,"metric":"median","layers":{"price":"평단가(만원/평)","vol":f"{CUR} 아파트 거래량(건)","yoy":"전년 대비 변동률(%)"}}, "districts":gu_prices})
dump("seoul_monthly.json", {"meta":meta,"series":seoul_monthly})
dump("gu_heatmap.json", {"meta":meta,"districts":hm_dist,"months":hm_months,"z":z,"unit":"거래량(건)"})
print(f"완료: {len(gu_prices)}구 · 월별 {len(seoul_monthly)} · 히트맵 {len(hm_dist)}x{len(hm_months)}", file=sys.stderr)
