"""TASK-054/055 boss data + phase framework: kits in data/bosses.py and entities/boss_attacks.py, the roster's phases.

GOLDEN was recorded with tests/boss_trace.py on main 1916a5f (the pre-054 Boss): every scripted fight hashes the boss
state, the global RNG state, the phase announces and every shot spawned, frame by frame. TASK-055 changes the phase
table on layers 4-10 (and layer 9's verdict pick), so exactly those wardens' fights have new digests in GOLDEN_055;
acts 0-2 and every mini-boss fight still hash as on main. TASK-057 makes each mini-boss a named anchor (roster name,
TASK-045 radius); GOLDEN_057 holds those fights ("mini" = the layer's first anchor, the new "mini_b" = its second).
"""
from __future__ import annotations

import math
import random

import pytest

from blob_evolution import config
from blob_evolution.data import bosses
from blob_evolution.data.lore import get_boss_name, get_warden_fragment_id
from blob_evolution.entities import boss_attacks
from blob_evolution.entities.boss import Boss
from blob_evolution.utils.vector2 import Vector2

from boss_trace import KINDS, SEEDS, fight_digest

GOLDEN = {
    "0/warden/3": "dd7059d2fe7f2093623707e47f0045abef3c8d51",
    "0/warden/17": "f5a91cfccaa57cc380c0bff1c78e9646e1880ca5",
    "0/warden/202": "4eb768a2cd8955c9be041cb6c851c0da158ab1a0",
    "0/warden/4711": "b712c1fbb042942eba6460e71dc96c68a5e252f1",
    "0/slot1/3": "4047f6663567deae7134d57487f8c759c975687e",
    "0/slot1/17": "714335f43fe9c37e1311420d5e98c12f3ea3dec6",
    "0/slot1/202": "fa56d143d5759dff04f3d53304c8614765b10a30",
    "0/slot1/4711": "2907bb712152727c08fb32b36a6b99cae3fd18c9",
    "0/slot2/3": "a1d01dd5d2f7c838001432fbb2d12d8ade921666",
    "0/slot2/17": "7ccdfdd78c8ea854467ffeec16b8f9108e8b7f22",
    "0/slot2/202": "671f313003d6c2e6cb6d8946e57edb5164b67609",
    "0/slot2/4711": "facdc98e2a63302d65490fbbda26b4f69174fd04",
    "0/mini/3": "9bd57f40ca21ddbd8c66820766007b8e116af11a",
    "0/mini/17": "b7c542847d124796a4e9a01e1118057c6f54c5f0",
    "0/mini/202": "63bca5cddf321f0d6cf14e557ab85a027195ad52",
    "0/mini/4711": "50912eabd8c1b749ec5f6e5d7afdae048e42dd80",
    "1/warden/3": "934dc72f72bbdc9ddb4953eec35d6ff823fd3c04",
    "1/warden/17": "8f8b45d67c0beb9626aafb0d2558e4531ec259b6",
    "1/warden/202": "005c04542277b7e2a8f2b17b3ce9f27afe8d6af9",
    "1/warden/4711": "60b1b9a37333e06e82e44ae9779a1652efdb7944",
    "1/slot1/3": "4c4909ea8c84fd9c6f1a20886828ba0dcf0c819c",
    "1/slot1/17": "b303f1786329c8d51160da994f3a30206dac1055",
    "1/slot1/202": "07c5685237eaac829cea92addc59f5fca93ff1b1",
    "1/slot1/4711": "ac2e6f387117471438880ca694afa0368ba0a786",
    "1/slot2/3": "f96fc9a3ce24376c043b7dc6bef590c1dc95ab35",
    "1/slot2/17": "6ed30df8a845f2e3a7bb99868a3c270d50ccfcc4",
    "1/slot2/202": "45326197619bb24dccc2fb4d7aa05dbf73013ef4",
    "1/slot2/4711": "2734113ea796da4cb921ae029cd26364be4eac7d",
    "1/mini/3": "b6377f19e4b7b1ab43f5da32fa91fbb36aa0f237",
    "1/mini/17": "31a0c186e2effcf8e9078a41e39bb1bc47e98b7d",
    "1/mini/202": "59c59022c04b18f026c03ec73b9e9c189b137eb8",
    "1/mini/4711": "479bb55b8a30e7452019390b24f0ff4e5c69fe61",
    "2/warden/3": "6976c837cab5c0ab54c0b5107fc2459c00d835aa",
    "2/warden/17": "60f0a84fd733a3dbd2f18dffd27e2a7ddd6f3512",
    "2/warden/202": "ffb683a40a8b2513d9dd96bc710791ed93df2c5e",
    "2/warden/4711": "85aa91b7a6b9f6bedfb4d6695b1ace71d47f672a",
    "2/slot1/3": "4cb6331c5580cc4dca1afc7c2aaf9424f2290172",
    "2/slot1/17": "731b4f1c68e5bf91271ccd6c78eab4bb8bcefc59",
    "2/slot1/202": "5493e5b7bb7454d35257c937ee0af2d7bbaea84b",
    "2/slot1/4711": "8e6106dc194ce0b530d1bffc251f39b760c88d0d",
    "2/slot2/3": "3a6a1a67d185018d4eac2d4466cc23f9f3f394d8",
    "2/slot2/17": "983186e602d53deae217ae775268e1a6b7d1ad93",
    "2/slot2/202": "4c2d527400dafe8abf8c0b0f6899bfe3ca309f7a",
    "2/slot2/4711": "da95ec5eaaec5b66509e0aa2e58c65b76dc72ff1",
    "2/mini/3": "2b88346654b988720d227f4685e22fa269d8bf0f",
    "2/mini/17": "5bea19c084d8cff8ed9c2518c49cc8337b35f710",
    "2/mini/202": "080937d1801c31c17efbefb0434956113820a088",
    "2/mini/4711": "80613259c76999d608aa47e7d966ea5c8c893dea",
    "3/warden/3": "48e4b9732dc32328691dcbc0154800b3ead4a354",
    "3/warden/17": "fe4f8bb8594d9fb37b4b2bee76a2da6438c30ce5",
    "3/warden/202": "73466e7a030e11926b344a78f7c26124cbd8cb88",
    "3/warden/4711": "cae257afd40cf15917baced39fd3745d56fd4dd7",
    "3/slot1/3": "c2baf49e16f63dea4a0d97c71e37dcee1289192e",
    "3/slot1/17": "df749b3f5a36dca18fff0a4383e409ff4549df1e",
    "3/slot1/202": "a39d75e6754b4876f461a4bf82be8affb251e8f7",
    "3/slot1/4711": "4c63d209cb61b7b28f58519ed4aa7ee4e8744770",
    "3/slot2/3": "247269a171bfa8fd46931128fe2e400cdcad0005",
    "3/slot2/17": "6722efd6a04b6df346cf32e011ffef0d3d28235f",
    "3/slot2/202": "87982d319a0011267b675d832bd64f71dab2d5e7",
    "3/slot2/4711": "1e23ffe9303946e17ab6906d7f12c50d0ec9632b",
    "3/mini/3": "6917be23151b102287c320d2e58f139d3a3aa257",
    "3/mini/17": "9ea4fb7642fbb493e112e0c04b3c46ae53a47db7",
    "3/mini/202": "786a7593c0921268b6f8edfcd671ccab52e2f362",
    "3/mini/4711": "0ce439e33df343cfa5a0330c106aa7f54d65dd73",
    "4/warden/3": "60b4b0ad5106d4de4bc322e81e3e291c43f5ff9d",
    "4/warden/17": "9c5edd752c09c660e1e38d3e434614c877961043",
    "4/warden/202": "1630ee06d716d88a97d9284d8f98d41b8b9799e4",
    "4/warden/4711": "f975c01a6bd88851841d54c643fe8e2ef8b32ec2",
    "4/slot1/3": "4646fa2d04dc65781bb172209b7a3084c9589034",
    "4/slot1/17": "93425ba05d0fcacd1a6442b741e5ff0e906a2e44",
    "4/slot1/202": "f126b34ca58406bcf2c8a81ee03d69cfc8c6a0e4",
    "4/slot1/4711": "50120a70fa4b4fa991724154c30649323a63eb25",
    "4/slot2/3": "a3de4d0be656dc1e1c3be7e673cd069740789824",
    "4/slot2/17": "fb78f3a6778aaf0fe2f45f84040f30c84f993307",
    "4/slot2/202": "39cae5f184b65d00a194166a20cdf1b11253bb90",
    "4/slot2/4711": "16f6cfed66a926cc7c7b5927ce959ef363d7d1b9",
    "4/mini/3": "5d35776f354e24b9a05e23aa8fd3286fa6cea4eb",
    "4/mini/17": "5a9484fc29e4f8e4f34b861ea898f6dafe84189b",
    "4/mini/202": "3db03aaa1f14f7ac48b6a8aad2f29b8929b0db95",
    "4/mini/4711": "aa2cfd253c2e7235cd3110b2bccb496997f5f20b",
    "5/warden/3": "6a01f508ec3e76bf1fa5fc0f8d0882f31cf64fbe",
    "5/warden/17": "d6779c0eec98d114b13b511ae51a8fa9d27944f7",
    "5/warden/202": "7324f490bee41f2ab019402d875cd5339c2fdcb1",
    "5/warden/4711": "700f11fd9c2f54661c01321c8460887bae36fbef",
    "5/slot1/3": "61fd082c3e199a06ad0083240401a3b92526e78f",
    "5/slot1/17": "79323c5a04103b12943710b6d316fb18de9c52d7",
    "5/slot1/202": "c515dd37ff579ca4119b9803bb69f34534e7ed0a",
    "5/slot1/4711": "9355508a58f6084f4b1628ad42f006ef2a772a9b",
    "5/slot2/3": "c415ed958011069a2b3a3f694c45ebb091043690",
    "5/slot2/17": "973fc026c58ad5ca20760ba6398d14b57a222639",
    "5/slot2/202": "0c51b740cd5e2858b6d04bfbccf8fa0e3833f555",
    "5/slot2/4711": "2a8c27eda1e8f5d18b08c24c0351c89436324fe8",
    "5/mini/3": "16c6605ce5f6687ea64ea0f5272682959a47efde",
    "5/mini/17": "dee3fd05267ebbaa1f66ef31f886f6c4959579fa",
    "5/mini/202": "126c6922247c93b7622fa7a842383e3a14ae8ec9",
    "5/mini/4711": "248026eb531ccf483f446a87fd6ca80def111571",
    "6/warden/3": "9663d0d6f56bf4978ab220d46830576e030cc69e",
    "6/warden/17": "2bc9e30ce6d3ddb6abf7810e4715977602b714c0",
    "6/warden/202": "15119169396a045e602dadace09aa449c960d649",
    "6/warden/4711": "aa8277b195104a1fb2a9eddf398ead6b7240f4c7",
    "6/slot1/3": "4551c140472b4e4aa8d002cd0064e5a3da294943",
    "6/slot1/17": "d15d58aa802d0dd1af9711fb7b4db0d282ed5efc",
    "6/slot1/202": "fb2bd5698e62b9da1a7b7adf7ccd833d9b544522",
    "6/slot1/4711": "865456e0e2ef257c94b9755250494aadc997b38a",
    "6/slot2/3": "6028286685b85763ac59b3c1edb88148db41f06d",
    "6/slot2/17": "632c095e6871b68a88a5d24b415441e5c7d05840",
    "6/slot2/202": "99d61e9f71782ab77c4afc6e49cbeb24a73c993e",
    "6/slot2/4711": "c48e9df4ce39a36bc5072c4ae4141d16017e4ff2",
    "6/mini/3": "766e685e1dff8aa32d2354ce3980e95ef2dc1f1e",
    "6/mini/17": "8d78a31b2bd5f87fb8705a4de3d7e4547843758d",
    "6/mini/202": "5062bbf215b6fa4a328dfa8ec040ad62fcb79b54",
    "6/mini/4711": "990cce27d374d93cccff8e91022b8e456ce83a68",
    "7/warden/3": "02abec9d673f7e24da43e4133f629d3e434e3496",
    "7/warden/17": "e429c0e3ba407b70f770114748b3d556ddb39709",
    "7/warden/202": "8fad5b0d9366b1c3aebac25e23e9e577773654da",
    "7/warden/4711": "0d63123e3d95d79dc0f8bdba648e305e8eb52e62",
    "7/slot1/3": "7029f969829f936bfc62981dbd76e71bbd8915bc",
    "7/slot1/17": "e8199970999fac6bcc2d9c942ff96ec98e836080",
    "7/slot1/202": "3f37c59bb8a8aa82ac74cf6cc78599d06b564cf6",
    "7/slot1/4711": "f044f99a70260c6a0b1a57a76d9bdcc70b462b63",
    "7/slot2/3": "c1a505da7f32b2b45ca711db9c0a4dc45b45bd2d",
    "7/slot2/17": "7a63aea60cd253c08c6b1d69d46dd7387f8ef2f3",
    "7/slot2/202": "e66aa1c66c670f54d4207d702629f0d213316cd7",
    "7/slot2/4711": "a419d99b5fca753f8a4e1096610b32cdc4906aba",
    "7/mini/3": "7a9b2f19f6afae6ec48c3df8d05ec05f7568fbc7",
    "7/mini/17": "82159c30eab55cbb16f449c1db0e748c5c30a86c",
    "7/mini/202": "df5ee21f8303f659c72f283ea2e94984544722ba",
    "7/mini/4711": "0685b8420c5cb0fc5ee44bc25e9a8c163155dff4",
    "8/warden/3": "4d1c2223ed06750a883d282488dba9f4a2365e75",
    "8/warden/17": "56f9f4b1ac394ade2efa5bb9820d04c14d75b856",
    "8/warden/202": "42b96b1521d78f3a81f24cb93a9d9d00f75ff016",
    "8/warden/4711": "85f71b372cb50fb314f996a68d103f7f72356462",
    "8/slot1/3": "20ae1bec28d5d1bfa8e5ac50235fda6c2ff1e0d9",
    "8/slot1/17": "c1cdc1346b275c7e83986210b4fe2cf7ff2a9eea",
    "8/slot1/202": "0ebcd3832de042c1465fc07bfce493b54eb6aa26",
    "8/slot1/4711": "6821e943c536bbd20ac4c96f5aed1bf8c435868e",
    "8/slot2/3": "c72db146cfd1169caaff5869e34d802d86501e57",
    "8/slot2/17": "280f13f62f558becfbaef29f83688f902f6055f2",
    "8/slot2/202": "e82ba4ad8829843c14e96bd74a01dd20916cbdb3",
    "8/slot2/4711": "0bba473fa70348f7ea470ee9f26a959f0bb7022b",
    "8/mini/3": "d5716c5ca43256bf31fb4ef614af3487ac9b4a7e",
    "8/mini/17": "b247f4fe3401eb46b4e1d25ecea07978a035c25d",
    "8/mini/202": "50ca7f5ab31fa2d1c78d0bafd479e7e30950a024",
    "8/mini/4711": "e6cb07650fd7a61f8bb216a135e937923b4d4d5f",
    "9/warden/3": "c0f817c582c278ccfb655e10e45f5e904748d539",
    "9/warden/17": "6721cd99952b4ff7ff984c64dd6ffd87e59faf37",
    "9/warden/202": "8bda2fbf88fb05327c8aa7abac3b203f96c01bd5",
    "9/warden/4711": "0d5ebaab665eed1a528a064cb1b9472e07281696",
    "9/slot1/3": "d17b6510afcbc974ae4dc35837101f02f7822946",
    "9/slot1/17": "0f31c5fc8bab5d0a8cff7fc2a6379cd5f73f7e7c",
    "9/slot1/202": "656f125752a3abb932eb99f8832dae5488de036c",
    "9/slot1/4711": "4363389f268a22edf274bcabfff3952a9b0f1192",
    "9/slot2/3": "a26bd2189a31029b5e5471f14ee2a308db060dfe",
    "9/slot2/17": "ea4f4c887b655320af49796707536376da2d932a",
    "9/slot2/202": "8634cd2a946ab0f2b79370817c0005b58fccf658",
    "9/slot2/4711": "c7f10abae6fb0a312d3d72312b90b0d5eae758b5",
    "9/mini/3": "652da5e3e38317939b005aba7d93fa8a9dfabeda",
    "9/mini/17": "ed3818e69e3dc40cd7a6ef86e261e9840004a33c",
    "9/mini/202": "7656c764dd4d130c676e160376c50a243e0482ec",
    "9/mini/4711": "cf150186d9e3cb30949584ef88291c27b42020d5",
}

# Recorded on task-055-boss-phases 2b4c276 (behaviour change: roster phase table + layer 9 verdict cycle).
GOLDEN_055 = {
    "3/slot1/3": "7180b016c2372fcdbb0df8835fbbbe5b438472f0",
    "3/slot1/17": "091a80ca2405744972c2772b8f18f59ec7ea82b7",
    "3/slot1/202": "30eda849fdb5de8a8364e479b5ce92b0d7189926",
    "3/slot1/4711": "d7223f5fb4ed1ed7bceddda6879270e576359c12",
    "3/slot2/3": "29c1ebc23e497a7b1d9fdaa5932cca66065d098d",
    "3/slot2/17": "29d49390fb5b25516c67b8315021932907773d16",
    "3/slot2/202": "7ea3a0b0348c997ad8d685a27fb384f4e534136f",
    "3/slot2/4711": "08e53b1bafb3f0ba7ae8cf259800abbd559394ff",
    "3/warden/3": "91a1aaac387b278d0f9ce25c4f35c71da85604d9",
    "3/warden/17": "fe14512eb686c0a7e940c840be597da8f3bbcc34",
    "3/warden/202": "87b2ff3a78b4c8d940f92e4d05d8331644293feb",
    "3/warden/4711": "491c0faec9ed43ca3459e9ec258affc947f86a50",
    "4/slot1/3": "e3574ecc62cd1a59aac2d1c04365ba6ad03d8ade",
    "4/slot1/17": "ad5d0c19f1f1bf09955ad50c2e5ed2b94d9ba06a",
    "4/slot1/202": "bfb4a01fbb7034fceea6ec7d4248dd57bc24e54d",
    "4/slot1/4711": "2c901d4beccffe37550e9bf5ea17e3e9c674cf89",
    "4/slot2/3": "d9570404605a21b1e513e6c243ff94abea32c9c2",
    "4/slot2/17": "79ba9bc74e66f2c21b1511322aae0bde6bbc55c1",
    "4/slot2/202": "3067c976ab16a5e1be5b5d99072d9d87282fdf9c",
    "4/slot2/4711": "e6e88343a2e3b845f11f32e0353153b6db57b15d",
    "4/warden/3": "3af01e4ce1f1ebb3713df719e32b6601599a81b1",
    "4/warden/17": "45b5543c874f2e3569ba46a78e8c9fcc46463e42",
    "4/warden/202": "9aa3c86ba38d33006a068674a983bae74a688c2e",
    "4/warden/4711": "1db82fdea86e523c803edb51473c2ce0f235cc73",
    "5/slot1/3": "7eee4ca54c84df47b3b356e4324191db70474a50",
    "5/slot1/17": "bf066ae45afdc08d2a4890f1c43052f8ac097d77",
    "5/slot1/202": "53adae7689644541c64a5c841fa4419d45a13f16",
    "5/slot1/4711": "4d997048d7261a754a4374c0c39307d5d462929f",
    "5/slot2/3": "d65e99e180f09f2012d04da3e7557bb71ef1c61b",
    "5/slot2/17": "d3cf321e118f444eb80608a2f7b6da28f81bd808",
    "5/slot2/202": "7a37132654f57f8b7a2bb83552b4eb1bc098a560",
    "5/slot2/4711": "f2b1af4993054d01e2c57ae144addffaefbfed31",
    "5/warden/3": "09feb73c1187d31e786a405d3dd655950fe41bfa",
    "5/warden/17": "81f7d70a5647ee766bac607c6d52afd9dff5d725",
    "5/warden/202": "796374c98a7b880838d03d8831f9df8db66a31bf",
    "5/warden/4711": "6e8cb198bbe37c30155c89538d55ecc752a89bd9",
    "6/slot1/3": "572eac1a0e5d72e1d5b2acce88afd312633a0e17",
    "6/slot1/17": "02652fbc66b20936903bdba2b6d6bd53603109f5",
    "6/slot1/202": "59d591c611416c1955d92e54656617011ab85b29",
    "6/slot1/4711": "eb5ca14ff76b6516d657dbda25df0a759d42e71d",
    "6/slot2/3": "bf4e7033b995c905d0a3831cf0c47ceb2bb78173",
    "6/slot2/17": "bb5737d325204569a8ec83713de48d635209206e",
    "6/slot2/202": "2d38440aa39408a242d05bfdeec4fe0815c220ab",
    "6/slot2/4711": "05797012fdd236501d3b2a663b3da12dd0d29af1",
    "6/warden/3": "5d73944c730f3e49a6492deb2f1cb5e9cf6ee2d1",
    "6/warden/17": "28e8036e3d4faa17b32970c1b0c35937f2ed0dee",
    "6/warden/202": "c25b18ffbdcd892ee88fcbdadfd1cde7ed1b782e",
    "6/warden/4711": "28cec35dde1a6970f535f0bfc39ab478eb363e9a",
    "7/slot1/3": "f70ec4b8472dcde1473a715e9f6dff8a875dbbe0",
    "7/slot1/17": "bcc17806c75518091bf030847e244648762dcddc",
    "7/slot1/202": "d2cdf7ea06041ebdd142dc0a25ff54c385bc7986",
    "7/slot1/4711": "17dd1e92a2258bd7fec9925a1e8f1edc0b2afc0d",
    "7/slot2/3": "a40c302418057474035a85082fd2d9162483a1d4",
    "7/slot2/17": "6e055f5a061d400204f5a4b53007efcf98615571",
    "7/slot2/202": "272bde40cf2cb5f0cbe45bcbe9427e20ad8e5a18",
    "7/slot2/4711": "ced82dd2462187cf72b1171d7ab36e6fa3fdbe40",
    "7/warden/3": "ef15dd798c93ba3b8a22c886ff397f43f77cb769",
    "7/warden/17": "caf8184105b1b245d335220bd6c2e99015537ad5",
    "7/warden/202": "5fd6765994b2cbbac27b3c5d00432e352aa5b3d5",
    "7/warden/4711": "021d21866a5129e2cf12afe35aec40b9c0249214",
    "8/slot1/3": "5ce53780058ed2dd1f0acc0fb7b9774cd2dca672",
    "8/slot1/17": "fe889e4991d832f540b00ed3853847b38fe9efa5",
    "8/slot1/202": "de1d4828b589968aa525a8193d84268b5688525f",
    "8/slot1/4711": "1ff61057236a8f4ee41975f7acf7fb8bca1eb0ad",
    "8/slot2/3": "9d337fb949b145446b3e59e9ca387e393a9419c6",
    "8/slot2/17": "282cbeaa393701419ba001e9470d1e9fe9ac3d98",
    "8/slot2/202": "1766f5f09636e8e2bfb164844f707bff298a5330",
    "8/slot2/4711": "300b9e5bc5d6cec8cabbdfcc69f9a2e8d3bd9c44",
    "8/warden/3": "d4f8da20e5943236708ec11cbc8c0e2afa0e63ff",
    "8/warden/17": "ac59b6f140d75bca5d40fa55ec78664f9a0f5762",
    "8/warden/202": "9e845d1cdbb2a0fec2d5b1d298ff551854968593",
    "8/warden/4711": "fed95f9101d05811c7bfcd19d53759d7feb8620d",
    "9/slot1/3": "7cbb7a853e8f403c306eeffad48a5f1de8123d88",
    "9/slot1/17": "7644445ecc105bf6c17cbeed5159795829de7dba",
    "9/slot1/202": "1cc54cb64d1313a28fecfdaf35d56b093c725fb1",
    "9/slot1/4711": "2fd394eaea061c134c2379b50459fe4c2f9703d1",
    "9/slot2/3": "eec5a74091e6cc921519848a1e599057d075fb86",
    "9/slot2/17": "163bd1960053a66d554fde22953024e82f2212b5",
    "9/slot2/202": "9bd755f11f506172c84eae582f022d6b3ed0b210",
    "9/slot2/4711": "95ab85856f66ffa65d99e73ece800cccafe8abc3",
    "9/warden/3": "f6a8c2371d1fca2fe37b670c5b2ab3dc972fa33f",
    "9/warden/17": "c5806b94a3c46c0ab534a066f48d5c36c7e89288",
    "9/warden/202": "98fcc4e2bb333cd2f4d8b6c0f1f5ac0c3b8d64e5",
    "9/warden/4711": "81e4b7671b814335652378c9808321be12fd3f53",
}
CHANGED_BY_055 = {f"{act}/{kind}/{seed}" for act in range(3, 10) for kind in ("warden", "slot1", "slot2") for seed in SEEDS}

# Recorded on task-057-mini-bosses f94d392: named anchors (name + TASK-045 radius); mini_b is new (second anchor).
GOLDEN_057 = {
    "0/mini/3": "9e03295f980cc26b4bd5e684571e51802d50d79c",
    "0/mini/17": "c638ed8e65e182f175b68f047ac1ad7669487066",
    "0/mini/202": "ba5ac726c73cfb17e9947d53aa2edfffc4b724ba",
    "0/mini/4711": "ae17ae35084ac0d9d63b60de1ab533694ad54d13",
    "1/mini/3": "a38c8ad4eeca22f1f2cbba811ec55a31671432be",
    "1/mini/17": "a715bbce320958b30e14388bed79786dc13927cf",
    "1/mini/202": "d97e8886f3727207ee43acf1f597d854fdf03a3a",
    "1/mini/4711": "69c8dff85337fc7c613deea722ba81cd5c00d7ee",
    "2/mini/3": "4b3ed030a858eceb4136ecc7b861a98475b2a91d",
    "2/mini/17": "78b7c73e8bd2e43bf3607795d6093c8db335fc3c",
    "2/mini/202": "d143cf8a2ea5a37147bde67978ee5996de8d8537",
    "2/mini/4711": "6ee2ceb3ba8254f7fba60d53f41ab4ec322b47f5",
    "3/mini/3": "df0915e958a16b523f494dffdc1d7282f8e9303c",
    "3/mini/17": "9a8fe8ab9b1c277c0ea45dc94009310a45bf4e68",
    "3/mini/202": "0024ff9034b3dd1f296a7cd5ce0b096eb818bc43",
    "3/mini/4711": "85927b2e149b4f76fbb8cea2a2371d13bc6f248a",
    "4/mini/3": "331d4d1bfd23c977ab74aa28d6fbb8670040e603",
    "4/mini/17": "b4bdb44771cb65d314d4e97c7e1b474219387bac",
    "4/mini/202": "63af4897318dd840af9fc2479f7b51539e4354ed",
    "4/mini/4711": "92d0b50961157246441003c618d1f4fcbd80582c",
    "5/mini/3": "6841356a2844f457e236e146dbc5335f3013a978",
    "5/mini/17": "2ebcd490833ecb1fa01a7e4405ed66a09f125fa3",
    "5/mini/202": "2b33aaedb44a32099dce310e14c0ae9b8147ac10",
    "5/mini/4711": "e3fb3ba09d88ead2648e875d07386c62bb392536",
    "6/mini/3": "76a25979c852a69370235b00945f84a89bbc699e",
    "6/mini/17": "1dd841f5efe4f48b00f032e448e7b15023b34a49",
    "6/mini/202": "c49de16edd7a4d145c0db3b2d3aab64632f0cabc",
    "6/mini/4711": "0878e0c72a1bdcc5efcb631cd6910d849fe5b205",
    "7/mini/3": "362dcb27621e5ea86f54774bf83dbce11b48a9e2",
    "7/mini/17": "46644b63e753583b2db1a42b3ee626b1c8f7a900",
    "7/mini/202": "ddd91e78dfa6c6279a4107ef49b20188f143bfde",
    "7/mini/4711": "c21c6c3771853a0589a1b0c27d3e294070b3d23c",
    "8/mini/3": "8372841babd8d5b81a1329b34155a35512127daf",
    "8/mini/17": "20bd23df2c381272f805f36f3ea8b881974030a9",
    "8/mini/202": "45be928d57da31e6f80bcf61589fa3c8977ef47d",
    "8/mini/4711": "67b924ecabea2eca3b3330c7a35307009e13da79",
    "9/mini/3": "b2afd9b77208dd067fa19a1a83dccc5c326b7e4d",
    "9/mini/17": "6d2eb6f22b24f6b9719eb24fe07fb53987940266",
    "9/mini/202": "862a89fb339eb5167d95e396ad449592dc1816a2",
    "9/mini/4711": "acbcd85cf3cb266e631753b83a53b7fe2f98424b",
    "0/mini_b/3": "bf3902a1968429ee39683beb4c864fe7289a63ab",
    "0/mini_b/17": "1e596b95a59fca6ea5f1625b1eb6930abd9b147d",
    "0/mini_b/202": "6b69ab572c4eae1f3c1768b3989847f11d3971a4",
    "0/mini_b/4711": "3d8463e150a98ea81792c9c55a6a8c98e6c8cd8e",
    "1/mini_b/3": "2bebca433cdedc3d90c7b669464c0e5587d2ae65",
    "1/mini_b/17": "1436d0747cd81a2f9f2ec591995ba49b817db3dd",
    "1/mini_b/202": "27560acc7077603cf22e104da738bb72f9539f1b",
    "1/mini_b/4711": "e7c06965837983b69eb30e84de53c31728f5e350",
    "2/mini_b/3": "7ec7b0fc34f4c1791943f61c22a04078fc24c066",
    "2/mini_b/17": "5e218c5cf38c30da9968de13fd115e9ab243f06e",
    "2/mini_b/202": "58a222ebbb1dbfd9f6eca18d051042ba683a9302",
    "2/mini_b/4711": "a74e35955816be5cdfbf435a424a39eec3971d60",
    "3/mini_b/3": "f72b4db7ecab4f811cbb0e4a571f2ab4d05678fa",
    "3/mini_b/17": "23fe0e77c438cbd852b38cfcb9296d7c16cf095f",
    "3/mini_b/202": "d0645c399662698606a095ac0077d0af44485b88",
    "3/mini_b/4711": "d59211a850093e8ed357fa51c88708c73fa5042e",
    "4/mini_b/3": "8c1373d9dbe92562f357e8ea6d508fda2bd3846e",
    "4/mini_b/17": "84735053e9b518b596a5a7afb408aa42bfc23443",
    "4/mini_b/202": "dcdff7e33a6fe60f13be46b4ecf023f0b545b0cb",
    "4/mini_b/4711": "ced7ad264d30ceeabcd4419d4b4158968d4bf5b5",
    "5/mini_b/3": "7b11dd396960804e8ff985c5ba9c341d3473e1b2",
    "5/mini_b/17": "77413aea3e179ecf4e943aaae4406a2b85060f06",
    "5/mini_b/202": "d1360db8441bf1a943beb911315375bb41a74900",
    "5/mini_b/4711": "607588e630f636b10d7ae408e2d0fc60c88e0d3d",
    "6/mini_b/3": "d4a0c004a22e08836bb130eafef7d56fa9d9d18c",
    "6/mini_b/17": "df0084e5fc8119839b5f9f554c31ba07e330b836",
    "6/mini_b/202": "493034acf94e0a64b7506add5af0fbd9073d97a0",
    "6/mini_b/4711": "e7d4c427689d070fbe86b8f9ed041f55b15d31ce",
    "7/mini_b/3": "57b53264732b5db5eac27c9bcfd621464829ebda",
    "7/mini_b/17": "1de5486da59fc4d4429e554a3f0d1b8084a9b351",
    "7/mini_b/202": "474ca03a6583e7edab5c820aa974660046d53f17",
    "7/mini_b/4711": "fe1c11cc0562d0cca4ccd7442f1cb34dd8393c64",
    "8/mini_b/3": "41e6b42f3171af46e226ecf4aa0634d648e0848d",
    "8/mini_b/17": "3095daa732200f08017499d6b2003fe2c139fd75",
    "8/mini_b/202": "928e0bfc08269df863b7ec0de5b445e82d08050e",
    "8/mini_b/4711": "7c93afe54e0195630958f7404b798316b2eb53da",
    "9/mini_b/3": "31071e2bde2a9a937de5878a6e520083c1faf5e8",
    "9/mini_b/17": "ac4a79d2ee68bb695ccdf36b08a49b079b0338ce",
    "9/mini_b/202": "c72affa1bc639c8ec2cd1da27997043199313351",
    "9/mini_b/4711": "84883ea92b6093e2c2351e9be3b00e67d4d9e0a6",
}
CHANGED_BY_057 = {f"{act}/{kind}/{seed}" for act in range(10) for kind in ("mini", "mini_b") for seed in SEEDS}

ARCHIVE_IDS = [f"warden_{i}" for i in range(10)]
ROSTER_PHASES = {act: ((2, 0.5),) for act in range(3)}                        # layers 1-3: 2 phases
ROSTER_PHASES.update({act: ((2, 0.5), (3, 0.25)) for act in range(3, 8)})    # layers 4-8: 3 phases
ROSTER_PHASES[8] = ((2, 0.66), (3, 0.33))                                     # layer 9 (Ascent / Echoes / Stillness)
ROSTER_PHASES[9] = ((2, 0.66), (3, 0.25))                                     # layer 10 (Producer ruling)


def _expected(key: str) -> str:
    """The digest a scripted fight must have on this branch."""
    return GOLDEN_057.get(key) or GOLDEN_055.get(key) or GOLDEN[key]


@pytest.mark.parametrize("act", range(10))
def test_scripted_fights_match_the_recorded_digests(act):
    """Every scripted fight hashes as recorded: main's digest, 055's where the phase table changed, 057's for anchors."""
    for kind in KINDS:
        for seed in SEEDS:
            key = f"{act}/{kind}/{seed}"
            assert fight_digest(act, kind, seed, draw=False) == _expected(key), key


def test_only_the_changed_phase_tables_changed_digests():
    """055 changed exactly the layer 4-10 warden fights (all slots); layers 1-3 and all mini-bosses are main's."""
    assert set(GOLDEN_055) == CHANGED_BY_055
    assert all(GOLDEN_055[k] != GOLDEN[k] for k in GOLDEN_055)
    assert set(GOLDEN_057) == CHANGED_BY_057 and not set(GOLDEN_057) & set(GOLDEN_055)        # 057: anchors only
    assert all(GOLDEN_057[k] != GOLDEN[k] for k in GOLDEN_057 if k.split("/")[1] == "mini")


def test_trace_sees_a_changed_shot():
    """The digest is sensitive: one shot with a different colour changes it."""
    real = boss_attacks.AimedShot.fire

    def tinted(self, b, to_player, projectiles):
        real(self, b, to_player, projectiles)
        projectiles[-1].color = (1, 2, 3)

    try:
        boss_attacks.AimedShot.fire = tinted
        assert fight_digest(3, "warden", SEEDS[0], draw=False) != _expected(f"3/warden/{SEEDS[0]}")
    finally:
        boss_attacks.AimedShot.fire = real


def test_archive_ids_stay_warden_0_to_9():
    """Save ids are unchanged: the data, the lore and the save hook all say warden_0..warden_9."""
    assert [d.archive_id for d in bosses.WARDENS] == ARCHIVE_IDS
    assert [get_warden_fragment_id(i) for i in range(10)] == ARCHIVE_IDS
    assert [d.act for d in bosses.WARDENS] == list(range(10))


def test_every_key_in_the_data_has_a_kit():
    """Each warden's mover, basic shot and special exist, and so does the mini-boss kit."""
    for d in bosses.WARDENS:
        assert d.move in boss_attacks.MOVERS and d.special in boss_attacks.SPECIALS
        assert d.basic in boss_attacks.BASIC_SHOTS
        assert d.basic_other_slots is None or d.basic_other_slots in boss_attacks.BASIC_SHOTS
    assert bosses.MINI.move in boss_attacks.MOVERS and bosses.MINI.special in boss_attacks.SPECIALS


@pytest.mark.parametrize("act", range(10))
def test_stats_are_the_old_formulas(act):
    """Radius, HP, damage, speed and XP equal main's formulas for slots 0-1; anchors keep main's mini HP and cadence."""
    diff = {"hp": 1.5, "damage": 1.2, "speed": 0.9}
    for slot in (0, 1):
        b = Boss(Vector2(500, 500), act, diff, slot=slot)
        p = act + slot
        want = (50 + p * 10, (300 + p * 100) * 1.5, (20 + p * 5) * 1.2, 60 * 0.9)
        assert (b.size, b.max_hp, b.damage, b.speed) == want
        assert b.radius == b.size and b.xp_value == int(b.max_hp) and b.name == get_boss_name(act, slot=slot)
    for variant in (0, 1):
        m = Boss(Vector2(500, 500), act, diff, miniboss=True, variant=variant)
        assert (m.size, m.max_hp) == (bosses.anchor_def(act, variant).radius, (300 + act * 100) * 1.5 * 0.55)
        assert (m.damage, m.speed, m.xp_value) == ((20 + act * 5) * 1.2, 60 * 0.9, int(m.max_hp))
        assert (m.shoot_cooldown, m.special_cooldown) == (1.5, 4.0)


@pytest.mark.parametrize("act", range(10))
def test_wardens_follow_the_roster_phase_table(act):
    """Each phase starts just under its threshold, once, with one announce and the configured special cooldown."""
    b = Boss(Vector2(500, 500), act, None)
    assert tuple((pd.phase, pd.below) for pd in b.phase_defs) == ROSTER_PHASES[act]
    hp_left = 1.0
    for phase, below in ROSTER_PHASES[act]:
        b.take_damage(b.max_hp * (hp_left - below - 0.005))
        hp_left = below + 0.005
        assert b.phase == phase - 1 and not b.consume_phase_announce()
        b.take_damage(b.max_hp * 0.01)
        hp_left -= 0.01
        cd = config.BOSS_PHASE2_SPECIAL_COOLDOWN if phase == 2 else config.BOSS_PHASE3_SPECIAL_COOLDOWN
        assert (b.phase, b.enraged, b.special_cooldown) == (phase, True, cd)
        assert b.consume_phase_announce() and not b.consume_phase_announce()
        b.special_cooldown = 9.0
        b.take_damage(b.max_hp * 0.01)
        hp_left -= 0.01
        assert b.special_cooldown == 9.0 and not b.consume_phase_announce()      # each phase starts only once
    b.take_damage(b.max_hp * (hp_left - 0.01))
    assert b.phase == len(ROSTER_PHASES[act]) + 1 and b.hp > 0


def test_layer_nine_is_one_body_with_three_names():
    """Warden of Ascent becomes Warden of Echoes at 66 % and Warden of Stillness at 33 %; its Archive id stays."""
    triad = ("Warden of Ascent", "Warden of Echoes", "Warden of Stillness")
    b = Boss(Vector2(500, 500), 8, None)
    assert b.name == triad[0] and b.defn.archive_id == "warden_8"
    b.take_damage(b.max_hp * 0.35)
    assert (b.phase, b.name) == (2, triad[1])
    b.take_damage(b.max_hp * 0.33)                                              # 65 % -> 32 %
    assert (b.phase, b.name) == (3, triad[2])
    for act in (0, 3, 7, 9):                                                    # nobody else is renamed
        o = Boss(Vector2(500, 500), act, None)
        name = o.name
        o.take_damage(o.max_hp * 0.8)
        assert o.name == name


@pytest.mark.parametrize("act", range(10))
def test_mini_bosses_keep_main_s_phases(act):
    """Lattice Anchor: 50 % on every layer, plus 25 % from layer 9 on, as on main, and never renamed."""
    m = Boss(Vector2(500, 500), act, None, miniboss=True)
    want = ((2, 0.5), (3, 0.25)) if act >= bosses.FINAL_PHASE_FROM_ACT else ((2, 0.5),)
    assert tuple((pd.phase, pd.below) for pd in m.phase_defs) == want
    assert all(pd.name is None for pd in m.phase_defs)


@pytest.mark.parametrize("slot", range(3))
def test_layer_nine_verdicts_cycle_through_all_three(slot):
    """Main played only the slot's verdict; now radial (10), targeted (5) and cross (12) take turns from the slot's."""
    random.seed(4)
    b = Boss(Vector2(1200, 1100), 8, None, slot=slot)
    sizes = {"radial": 10, "targeted": 5, "cross": 12}
    seen = []
    for _ in range(6):
        shots: list = []
        b._special_attack(Vector2(900, 900), shots)
        seen.append(len(shots))
    order = [sizes[k] for k in config.BOSS_VERDICT_ORDER]
    assert seen == [order[(slot + i) % 3] for i in range(6)] and b.specials_fired == 6


def test_one_big_hit_runs_both_phase_starts_in_order():
    """A hit from full HP to 20 % enrages and lands in the last phase: 3 on layers 5, 9 and 10, 2 on layer 2. BUG-147: both
    starts are kept in order, each with its name and the special cooldown it applied (P2's 1.5, then P3's 1.0)."""
    p2, p3 = config.BOSS_PHASE2_SPECIAL_COOLDOWN, config.BOSS_PHASE3_SPECIAL_COOLDOWN
    for act, phase in ((9, 3), (8, 3), (4, 3), (1, 2)):
        b = Boss(Vector2(500, 500), act, None)
        first = b.name
        b.take_damage(b.max_hp * 0.8)
        assert (b.phase, b.enraged) == (phase, True)
        starts = b.take_phase_starts()
        if phase == 2:
            assert starts == [(2, first, p2)] and b.special_cooldown == p2
            continue
        name2 = "Warden of Echoes" if act == 8 else first
        name3 = "Warden of Stillness" if act == 8 else first
        assert starts == [(2, name2, p2), (3, name3, p3)], (act, starts)
        assert b.special_cooldown == p3 and b.name == name3
        assert b.take_phase_starts() == [] and not b.consume_phase_announce()


@pytest.mark.parametrize("act", [1, 4, 8, 9])
def test_a_hit_landing_exactly_on_a_threshold_does_not_start_the_phase(act):
    """BUG-149: phases start strictly below the threshold (as main): a hit landing exactly on it keeps the old phase, the next
    hit under it starts the phase. max_hp = 100 and whole-number HP make the ratio exactly the table's float."""
    for pd in Boss(Vector2(500, 500), act, None).phase_defs:
        on = round(pd.below * 100)
        assert on / 100 == pd.below
        b = Boss(Vector2(500, 500), act, None)
        b.max_hp, b.hp = 100.0, float(on + 2)
        b.phase, b.enraged = pd.phase - 1, pd.phase > 2
        b.take_damage(2.0)
        assert b.hp / b.max_hp == pd.below
        assert b.phase == pd.phase - 1 and b.take_phase_starts() == [], (act, pd.phase)
        b.take_damage(0.5)
        assert b.phase == pd.phase and [st[0] for st in b.take_phase_starts()] == [pd.phase], (act, pd.phase)


def test_phase_three_needs_the_crossing_hit():
    """HP already under 25 % without a crossing hit (as main) does not start phase 3."""
    b = Boss(Vector2(500, 500), 9, None)
    b.hp = b.max_hp * 0.2
    b.take_damage(1.0)
    assert (b.phase, b.enraged) == (2, True)


@pytest.mark.parametrize("enraged,phase,mini,basic,special", [
    (False, 1, False, 1.7, 5.2), (True, 2, False, 1.2, 3.2), (True, 3, False, 1.2 * 0.75, 3.2 * 0.7),
    (False, 1, True, 1.7 * 1.2, 5.2 * 1.15), (True, 3, True, 1.2 * 0.75 * 1.2, 3.2 * 0.7 * 1.15),
])
def test_cooldowns_after_firing(enraged, phase, mini, basic, special):
    """Basic and special cooldowns use main's bases and multipliers, in main's order."""
    random.seed(1)
    b = Boss(Vector2(500, 500), 9, None, miniboss=mini)
    b.enraged, b.phase = enraged, phase
    b.shoot_cooldown = b.special_cooldown = 0.0
    shots: list = []
    b.update(1e-6, Vector2(900, 500), shots)
    assert shots and (b.shoot_cooldown, b.special_cooldown) == (basic, special)


def test_mini_bosses_keep_their_layers_basic_shot_and_the_radial_special():
    """Lattice Anchor: the layer's basic shot, orbit movement and the 6-way radial."""
    for act in range(10):
        m = Boss(Vector2(500, 500), act, None, miniboss=True)
        assert m.special.key == "anchor_radial" and m.mover is boss_attacks.move_orbit
        assert m.basic_shot.key == bosses.WARDENS[act].basic
    assert Boss(Vector2(500, 500), 8, None, slot=1).basic_shot.key == "aimed"


@pytest.mark.parametrize("act", [-1, 10, 12])
def test_acts_outside_the_table_get_main_s_fallback_kit(act):
    """Out-of-range acts (generator.spawn_bosses can make them) still fight: aimed shot, Divide special."""
    random.seed(2)
    b = Boss(Vector2(500, 500), act, None)
    assert b.basic_shot.key == "aimed" and b.special.key == "divide" and b.mover is boss_attacks.move_assault
    assert len(b.phase_defs) == (2 if act >= 8 else 1)
    shots: list = []
    b.shoot_cooldown = b.special_cooldown = 0.0
    b.update(1 / 60, Vector2(900, 700), shots)
    assert len(shots) == 1 + 14 + 3 and math.isclose(shots[0].damage, b.damage)
