
from matplotlib.colors import LinearSegmentedColormap
from numpy import nan, inf

# Used to reconstruct the colormap in viscm
parameters = {'xp': [-6.1859603226509137, -14.579245694353546, -16.377806845432701, -75.430564639197684, 40.576629605406652, 14.197732722912633],
              'yp': [-38.399280575539549, 5.6654676258992822, 11.061151079136692, 51.229016786570725, 35.641486810551555, -4.8261390887290077],
              'min_JK': 27.8125,
              'max_JK': 87.2916666667}

cm_data = [[ 0.08488181,  0.18308161,  0.67262216],
       [ 0.08312345,  0.19202711,  0.66090297],
       [ 0.08217997,  0.20014429,  0.64976469],
       [ 0.08198433,  0.2075936 ,  0.63911277],
       [ 0.08247594,  0.21447696,  0.62891889],
       [ 0.08359003,  0.2208603 ,  0.61920504],
       [ 0.08524777,  0.2268386 ,  0.60985788],
       [ 0.08738166,  0.23244191,  0.60093206],
       [ 0.08992038,  0.2377215 ,  0.59238917],
       [ 0.09280155,  0.24272587,  0.58416923],
       [ 0.09596381,  0.24747257,  0.57631143],
       [ 0.0993575 ,  0.251998  ,  0.56876406],
       [ 0.10293853,  0.25632645,  0.56150762],
       [ 0.10666336,  0.2604716 ,  0.55456023],
       [ 0.1105036 ,  0.26445857,  0.54787429],
       [ 0.11443019,  0.26830128,  0.54144512],
       [ 0.11841518,  0.27200976,  0.53528253],
       [ 0.12244369,  0.27560103,  0.5293494 ],
       [ 0.12649882,  0.27908535,  0.52363821],
       [ 0.13056226,  0.28246931,  0.51815934],
       [ 0.13462547,  0.28576389,  0.51289008],
       [ 0.13868224,  0.28897881,  0.50780839],
       [ 0.14271871,  0.2921176 ,  0.50293114],
       [ 0.14672864,  0.29518709,  0.49824894],
       [ 0.15071345,  0.29819656,  0.4937278 ],
       [ 0.1546626 ,  0.30114819,  0.48938498],
       [ 0.15857184,  0.30404672,  0.48521597],
       [ 0.16243974,  0.30689736,  0.48120845],
       [ 0.16626692,  0.3097055 ,  0.47734461],
       [ 0.17004651,  0.31247292,  0.47363702],
       [ 0.17377693,  0.31520325,  0.47007969],
       [ 0.1774579 ,  0.31790023,  0.46666296],
       [ 0.18109034,  0.32056767,  0.46337356],
       [ 0.18466948,  0.32320706,  0.46022069],
       [ 0.18819439,  0.3258211 ,  0.4571996 ],
       [ 0.19166421,  0.32841234,  0.45430585],
       [ 0.19508052,  0.33098399,  0.4515254 ],
       [ 0.19844012,  0.33353749,  0.44886326],
       [ 0.20174153,  0.33607477,  0.44631801],
       [ 0.20498379,  0.3385979 ,  0.44388601],
       [ 0.20816589,  0.3411088 ,  0.44156374],
       [ 0.21128813,  0.34360991,  0.43934139],
       [ 0.21434794,  0.34610257,  0.43722134],
       [ 0.21734359,  0.34858841,  0.43520227],
       [ 0.22027364,  0.35106916,  0.433281  ],
       [ 0.22313653,  0.35354653,  0.43145439],
       [ 0.22593054,  0.3560222 ,  0.42971931],
       [ 0.22865443,  0.35849817,  0.42806853],
       [ 0.23130553,  0.36097577,  0.42650261],
       [ 0.23388157,  0.36345656,  0.42501923],
       [ 0.23638033,  0.36594216,  0.42361498],
       [ 0.23879948,  0.36843418,  0.42228628],
       [ 0.24113658,  0.37093422,  0.42102943],
       [ 0.24338915,  0.37344386,  0.41984053],
       [ 0.24555463,  0.37596471,  0.41871526],
       [ 0.2476304 ,  0.37849855,  0.41764727],
       [ 0.24961385,  0.3810466 ,  0.41663458],
       [ 0.25150254,  0.38361032,  0.41567235],
       [ 0.25329409,  0.38619113,  0.41475548],
       [ 0.25498629,  0.38879034,  0.41387864],
       [ 0.25657711,  0.39140923,  0.41303625],
       [ 0.25806477,  0.39404893,  0.41222253],
       [ 0.25944772,  0.3967105 ,  0.41143149],
       [ 0.26072475,  0.39939485,  0.41065702],
       [ 0.26189499,  0.40210277,  0.40989287],
       [ 0.26295789,  0.4048349 ,  0.40913271],
       [ 0.26391332,  0.40759175,  0.40837023],
       [ 0.2647615 ,  0.41037366,  0.40759912],
       [ 0.26550293,  0.41318086,  0.40681296],
       [ 0.2661385 ,  0.41601343,  0.40600552],
       [ 0.26666972,  0.41887118,  0.40517133],
       [ 0.26709825,  0.42175387,  0.40430471],
       [ 0.26742604,  0.42466112,  0.40340023],
       [ 0.26765527,  0.42759246,  0.40245273],
       [ 0.26778838,  0.43054729,  0.40145736],
       [ 0.26782797,  0.43352494,  0.40040961],
       [ 0.2677768 ,  0.43652465,  0.39930525],
       [ 0.26763777,  0.4395456 ,  0.3981404 ],
       [ 0.26741386,  0.44258692,  0.39691145],
       [ 0.26710811,  0.4456477 ,  0.39561511],
       [ 0.26672365,  0.448727  ,  0.39424836],
       [ 0.26626363,  0.45182384,  0.39280844],
       [ 0.26573088,  0.45493737,  0.39129233],
       [ 0.26512858,  0.4580666 ,  0.38969761],
       [ 0.26446024,  0.46121045,  0.38802247],
       [ 0.26372917,  0.46436794,  0.38626487],
       [ 0.26293876,  0.46753805,  0.38442293],
       [ 0.26209248,  0.47071979,  0.38249482],
       [ 0.26119391,  0.47391216,  0.38047885],
       [ 0.26024678,  0.47711415,  0.37837332],
       [ 0.25925503,  0.48032474,  0.37617663],
       [ 0.25822279,  0.48354291,  0.37388717],
       [ 0.25715449,  0.48676763,  0.37150332],
       [ 0.25605486,  0.48999782,  0.3690235 ],
       [ 0.25492731,  0.4932329 ,  0.36644367],
       [ 0.2537774 ,  0.49647174,  0.36376208],
       [ 0.25261249,  0.49971279,  0.36097881],
       [ 0.25143921,  0.50295487,  0.35809205],
       [ 0.25026483,  0.50619673,  0.35509995],
       [ 0.24909736,  0.50943704,  0.35200056],
       [ 0.24794283,  0.51267518,  0.34878753],
       [ 0.24681094,  0.5159097 ,  0.3454584 ],
       [ 0.24571493,  0.51913835,  0.34201468],
       [ 0.24466674,  0.52235947,  0.33845417],
       [ 0.24367796,  0.52557168,  0.33477178],
       [ 0.24275902,  0.52877417,  0.33095718],
       [ 0.24193144,  0.53196339,  0.32701729],
       [ 0.24121292,  0.53513707,  0.32294975],
       [ 0.24061591,  0.53829468,  0.31873685],
       [ 0.24016739,  0.54143201,  0.3143868 ],
       [ 0.23989167,  0.54454583,  0.3098995 ],
       [ 0.23980621,  0.54763531,  0.3052503 ],
       [ 0.23994718,  0.55069438,  0.30045852],
       [ 0.24033897,  0.55372091,  0.29550373],
       [ 0.24101659,  0.5567097 ,  0.29039154],
       [ 0.242013  ,  0.55965658,  0.28511189],
       [ 0.24336597,  0.56255578,  0.27966796],
       [ 0.24511307,  0.56540212,  0.27404701],
       [ 0.24729554,  0.56818809,  0.26826528],
       [ 0.24995455,  0.57090763,  0.26229943],
       [ 0.25313183,  0.57355191,  0.25617055],
       [ 0.25686732,  0.57611234,  0.24988551],
       [ 0.26120079,  0.57857967,  0.24344791],
       [ 0.26616801,  0.58094374,  0.23687306],
       [ 0.27179453,  0.58319423,  0.23019404],
       [ 0.27809821,  0.58532092,  0.22344485],
       [ 0.28508368,  0.5873143 ,  0.21667129],
       [ 0.29273881,  0.58916631,  0.20993178],
       [ 0.3010319 ,  0.5908713 ,  0.20329682],
       [ 0.30991056,  0.5924269 ,  0.19684672],
       [ 0.31930301,  0.59383467,  0.19066735],
       [ 0.32912207,  0.5951003 ,  0.18484441],
       [ 0.33927145,  0.59623329,  0.17945707],
       [ 0.34965323,  0.59724611,  0.17457225],
       [ 0.36017498,  0.59815298,  0.17024054],
       [ 0.37075539,  0.59896866,  0.16649448],
       [ 0.38132758,  0.59970726,  0.16334908],
       [ 0.39183913,  0.60038173,  0.1608045 ],
       [ 0.40223125,  0.60100791,  0.15885843],
       [ 0.41249475,  0.60159175,  0.15747918],
       [ 0.42261595,  0.60214034,  0.15663827],
       [ 0.43255125,  0.60266853,  0.15631551],
       [ 0.44232961,  0.60317358,  0.15646484],
       [ 0.45192221,  0.60366715,  0.15705899],
       [ 0.46135476,  0.60414659,  0.15805779],
       [ 0.47059963,  0.60462352,  0.1594324 ],
       [ 0.47969294,  0.60509169,  0.16114641],
       [ 0.48861904,  0.60555917,  0.16317152],
       [ 0.49738619,  0.60602708,  0.16547858],
       [ 0.5060124 ,  0.60649316,  0.16804181],
       [ 0.51450148,  0.60695916,  0.17083789],
       [ 0.52283993,  0.60743236,  0.17384267],
       [ 0.53105197,  0.60790769,  0.17703821],
       [ 0.53914308,  0.60838578,  0.18040711],
       [ 0.54711786,  0.60886742,  0.18393356],
       [ 0.55498092,  0.60935321,  0.18760336],
       [ 0.5627368 ,  0.60984364,  0.19140384],
       [ 0.57038905,  0.61033941,  0.19532343],
       [ 0.57793913,  0.61084192,  0.19935102],
       [ 0.58539646,  0.61134942,  0.20347965],
       [ 0.59276492,  0.61186207,  0.20770171],
       [ 0.6000482 ,  0.61237999,  0.21201055],
       [ 0.60724981,  0.61290327,  0.2164004 ],
       [ 0.61437307,  0.61343197,  0.22086628],
       [ 0.62142114,  0.61396611,  0.22540392],
       [ 0.62839694,  0.61450572,  0.23000966],
       [ 0.63530325,  0.61505081,  0.23468046],
       [ 0.64214263,  0.61560141,  0.23941375],
       [ 0.64891741,  0.61615756,  0.24420741],
       [ 0.65562676,  0.61672066,  0.24905779],
       [ 0.66227569,  0.61728944,  0.25396539],
       [ 0.66886611,  0.61786396,  0.2589293 ],
       [ 0.67539975,  0.61844427,  0.2639489 ],
       [ 0.68187814,  0.61903047,  0.26902384],
       [ 0.68830265,  0.61962269,  0.27415403],
       [ 0.69467448,  0.62022108,  0.27933959],
       [ 0.70099464,  0.62082585,  0.28458084],
       [ 0.70726401,  0.62143724,  0.28987828],
       [ 0.71348256,  0.62205592,  0.29523192],
       [ 0.71964871,  0.6226833 ,  0.30064055],
       [ 0.7257661 ,  0.62331815,  0.30610795],
       [ 0.73183497,  0.62396086,  0.3116352 ],
       [ 0.7378554 ,  0.62461192,  0.31722351],
       [ 0.74382734,  0.62527185,  0.32287414],
       [ 0.74975057,  0.62594124,  0.32858846],
       [ 0.75562355,  0.62662141,  0.33436653],
       [ 0.76144581,  0.62731307,  0.34020972],
       [ 0.76721835,  0.62801608,  0.34612142],
       [ 0.77294038,  0.62873127,  0.35210319],
       [ 0.77861095,  0.62945956,  0.35815664],
       [ 0.78422899,  0.63020192,  0.36428337],
       [ 0.78979252,  0.63095987,  0.37048392],
       [ 0.79530062,  0.63173429,  0.37676038],
       [ 0.80075261,  0.63252589,  0.38311548],
       [ 0.80614684,  0.63333595,  0.3895508 ],
       [ 0.81148155,  0.63416582,  0.39606787],
       [ 0.81675483,  0.63501695,  0.40266817],
       [ 0.82196435,  0.63589105,  0.40935253],
       [ 0.8271086 ,  0.6367893 ,  0.41612348],
       [ 0.83218532,  0.63771334,  0.42298234],
       [ 0.83719205,  0.63866495,  0.42993032],
       [ 0.84212626,  0.63964598,  0.43696849],
       [ 0.84698539,  0.64065826,  0.44409811],
       [ 0.85176681,  0.64170366,  0.45132049],
       [ 0.85646749,  0.64278436,  0.45863614],
       [ 0.86108437,  0.64390252,  0.46604562],
       [ 0.86561427,  0.64506041,  0.47354929],
       [ 0.87005391,  0.64626036,  0.48114736],
       [ 0.87440033,  0.6475044 ,  0.48884145],
       [ 0.8786496 ,  0.64879536,  0.49663003],
       [ 0.88279806,  0.65013581,  0.50451251],
       [ 0.886842  ,  0.6515284 ,  0.51248812],
       [ 0.8907776 ,  0.65297579,  0.52055578],
       [ 0.89460109,  0.65448064,  0.52871468],
       [ 0.89830854,  0.65604567,  0.53696351],
       [ 0.90189577,  0.65767392,  0.54529885],
       [ 0.90535877,  0.65936821,  0.5537181 ],
       [ 0.90869358,  0.66113137,  0.56221825],
       [ 0.91189625,  0.66296617,  0.57079586],
       [ 0.91496291,  0.6648754 ,  0.57944686],
       [ 0.91788981,  0.66686181,  0.5881658 ],
       [ 0.92067342,  0.66892797,  0.59694738],
       [ 0.92331042,  0.67107632,  0.60578593],
       [ 0.92579776,  0.67330909,  0.6146753 ],
       [ 0.92813267,  0.67562834,  0.62360891],
       [ 0.93031328,  0.678036  ,  0.63257538],
       [ 0.93233787,  0.68053348,  0.64156724],
       [ 0.93420501,  0.68312189,  0.65057749],
       [ 0.93591386,  0.68580207,  0.65959765],
       [ 0.93746411,  0.6885745 ,  0.66861913],
       [ 0.93885727,  0.69143911,  0.67762793],
       [ 0.94009655,  0.69439504,  0.686608  ],
       [ 0.94118182,  0.69744174,  0.69555831],
       [ 0.94211522,  0.70057808,  0.70447036],
       [ 0.94289928,  0.70380263,  0.71333615],
       [ 0.94354455,  0.70711146,  0.72212851],
       [ 0.94405369,  0.71050244,  0.73084569],
       [ 0.9444278 ,  0.71397394,  0.73948938],
       [ 0.94467085,  0.7175234 ,  0.74805426],
       [ 0.94480169,  0.72114324,  0.75650653],
       [ 0.94482174,  0.72483132,  0.76485204],
       [ 0.94472934,  0.72858669,  0.77310077],
       [ 0.94453501,  0.73240424,  0.78124012],
       [ 0.94426678,  0.73627241,  0.78923231],
       [ 0.9439052 ,  0.74019659,  0.79711843],
       [ 0.9434584 ,  0.74417245,  0.80489253],
       [ 0.94297022,  0.74818241,  0.81250113],
       [ 0.94240599,  0.75223783,  0.82000299],
       [ 0.94178596,  0.75632991,  0.82737865],
       [ 0.94114205,  0.76044536,  0.83459832],
       [ 0.94043604,  0.76459737,  0.84171794],
       [ 0.93972281,  0.76876404,  0.84868276],
       [ 0.93897849,  0.77295334,  0.85553024],
       [ 0.93820719,  0.77716269,  0.86226445],
       [ 0.93745099,  0.78137511,  0.86885223],
       [ 0.93665014,  0.7856125 ,  0.87536218]]

test_cm = LinearSegmentedColormap.from_list(__file__, cm_data)


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import numpy as np

    try:
        from viscm import viscm
        viscm(test_cm)
    except ImportError:
        print("viscm not found, falling back on simple display")
        plt.imshow(np.linspace(0, 100, 256)[None, :], aspect='auto',
                   cmap=test_cm)
    plt.show()
