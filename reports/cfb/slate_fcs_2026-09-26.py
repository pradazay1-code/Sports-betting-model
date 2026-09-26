"""FCS slate, Sat 2026-09-26. Market data RETRIEVED via web search 2026-09-26.
sp = HOME spread (negative = home favored). Away favorites show a POSITIVE sp.
Nothing estimated. Games with no retrievable market are in FCS_NO_MARKET."""

FCS = [
 dict(a="North Dakota",     h="Indiana State",   et="13:00", sp=16.5, tot=58.5, mlh=710,  mla=-1320,
      to=-104, tu=-119, spa=-111, sph=-111, conf="MVFC", n="UND favored on the road"),
 dict(a="Chattanooga",      h="The Citadel",     et="14:00", sp=11.5, tot=47.5, mlh=286,  mla=-385,
      to=-104, tu=-111, conf="SoCon",
      n="SHOPPABLE: CHAT -11.5 (-111) at one book, CIT +10.5 (-132) at another - market is 10.5/11.5"),
 dict(a="Furman",           h="Richmond",        et="14:00", sp=-3.0, tot=44.5, mlh=-152, mla=122,
      conf="SoCon/CAA", n="FUR 2-2 (1-1 away), RICH 3-1 (2-0 home)"),
 dict(a="Colgate",          h="Villanova",       et="14:30", sp=-10.5, tot=49.5, conf="Patriot/CAA"),
 dict(a="Montana",          h="UC Davis",        et="16:00", sp=-2.5, tot=None, conf="Big Sky",
      n="total NOT retrieved. Montana travels DOWN in elevation (3,200ft -> ~50ft)"),
 dict(a="Illinois State",   h="Northern Iowa",   et="16:00", sp=19.5, tot=58.5, mlh=700, mla=-1280,
      conf="MVFC", n="ISU favored on the road; UNI-Dome is indoor - weather is a non-factor"),
 dict(a="Southern Illinois",h="Murray State",    et="16:00", sp=16.5, tot=53.5, mlh=505, mla=-790,
      to=-111, tu=-111, spa=-120, sph=-104, conf="MVFC", n="SIU favored on the road; SIU 2-2, MUR 1-3"),
 dict(a="Maine",            h="Elon",            et="16:00", sp=-5.5, tot=44.5, mlh=-209, mla=165,
      to=-111, tu=-111, sph=-116, spa=-107, conf="CAA"),
 dict(a="Stony Brook",      h="Fordham",         et="17:00", sp=10.5, tot=52.5, mlh=313, mla=-429,
      to=-144, tu=116, spa=-111, sph=-111, conf="CAA/Patriot",
      n="SBU favored on road. TOTAL JUICE IS LOPSIDED: over -144 / under +116"),
 dict(a="South Dakota",     h="Youngstown State",et="18:00", sp=-1.5, tot=65.5, conf="MVFC",
      n="HIGHEST TOTAL OF THE ENTIRE DAY, FBS or FCS"),
 dict(a="Southern",         h="Jackson State",   et="18:00", sp=-20.5, tot=57.5, mlh=-1200, mla=670,
      conf="SWAC", n="JSU 3-0 at home, SO 2-2 away. JSU opens SWAC play"),
 dict(a="Western Carolina", h="East Tennessee St",et="18:00", sp=-1.5, tot=63.5, mlh=-128, mla=103,
      to=-116, tu=-107, sph=-112, conf="SoCon", n="both 2-2; WCU 2-0 away, ETSU 2-1 home"),
 dict(a="Northern Arizona", h="Montana State",   et="15:00", sp=-20.5, tot=56.5, mlh=-1724, mla=783,
      conf="Big Sky", n="NAU is a HIGH-ALTITUDE program (Flagstaff). MSU's altitude edge is neutralised."),
]

# Identified on the slate, NO market retrievable. Listed, never estimated.
FCS_NO_MARKET = [
 ("Cal Poly","Eastern Washington","Big Sky"), ("Idaho State","Southern Utah","Big Sky"),
 ("Portland State","Weber State","Big Sky"), ("Utah Tech","Northern Colorado","Big Sky"),
 ("East Texas A&M","McNeese","Southland"), ("Lamar","Nicholls","Southland"),
 ("Southeastern Louisiana","Northwestern State","Southland"), ("Sacramento State","UTRGV","Southland/ind"),
 ("Texas Southern","Alcorn State","SWAC"), ("Holy Cross","Lafayette","Patriot"),
 ("Columbia","Georgetown","Ivy/Patriot"), ("Lehigh","Penn","Patriot/Ivy"),
 ("UAlbany","Princeton","CAA/Ivy"), ("Monmouth","Dartmouth","CAA/Ivy"),
 ("Campbell","Hampton","CAA"), ("VMI","Samford","SoCon"), ("Tennessee Tech","Wofford","SoCon"),
]

# FBS-vs-FCS money games (the FCS side of the FBS slate) - already in the FBS sheet.
MONEY_GAMES = ["Bucknell @ Pittsburgh (-53.5)", "Central Arkansas @ Florida State (-45.5)",
               "William & Mary @ Duke (-43.5)", "Missouri State @ SMU (-34.5)"]
