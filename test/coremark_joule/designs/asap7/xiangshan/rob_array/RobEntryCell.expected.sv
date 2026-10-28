module RobEntryCell(
  input           clock,
                  reset,
  input  [8:0]    io_idx,
  input  [1218:0] io_in,
  output [30:0]   io_entry
);

  reg        entry_vls;
  reg        entry_interrupt_safe;
  reg  [3:0] entry_traceBlockInPipe_itype;
  reg  [5:0] entry_traceBlockInPipe_iretire;
  reg        entry_traceBlockInPipe_ilastsize;
  reg        entry_valid;
  reg  [4:0] entry_fflags;
  reg        entry_vxsat;
  reg  [3:0] entry_realDestSize;
  reg  [4:0] entry_uopNum;
  reg        entry_needFlush;
  wire       enqOH_0 = io_in[980] & io_in[979] & io_in[946] & io_in[882:874] == io_idx;
  wire       enqOH_1 = io_in[1014] & io_in[1013] & io_in[946] & io_in[891:883] == io_idx;
  wire       enqOH_2 = io_in[1048] & io_in[1047] & io_in[946] & io_in[900:892] == io_idx;
  wire       enqOH_3 = io_in[1082] & io_in[1081] & io_in[946] & io_in[909:901] == io_idx;
  wire       enqOH_4 = io_in[1116] & io_in[1115] & io_in[946] & io_in[918:910] == io_idx;
  wire       enqOH_5 = io_in[1150] & io_in[1149] & io_in[946] & io_in[927:919] == io_idx;
  wire       enqOH_6 = io_in[1184] & io_in[1183] & io_in[946] & io_in[936:928] == io_idx;
  wire       enqOH_7 = io_in[1218] & io_in[1217] & io_in[946] & io_in[945:937] == io_idx;
  wire [7:0] _enqHit_T =
    {enqOH_7, enqOH_6, enqOH_5, enqOH_4, enqOH_3, enqOH_2, enqOH_1, enqOH_0};
  wire       _GEN = (|_enqHit_T) & ~(io_in[865]);
  wire       uopEnqValidSeq_0 = io_in[946] & io_in[980];
  wire       uopEnqValidSeq_1 = io_in[946] & io_in[1014];
  wire       uopEnqValidSeq_2 = io_in[946] & io_in[1048];
  wire       uopEnqValidSeq_3 = io_in[946] & io_in[1082];
  wire       uopEnqValidSeq_4 = io_in[946] & io_in[1116];
  wire       uopEnqValidSeq_5 = io_in[946] & io_in[1150];
  wire       uopEnqValidSeq_6 = io_in[946] & io_in[1184];
  wire       uopEnqValidSeq_7 = io_in[946] & io_in[1218];
  wire       robIdxMatchSeq_0 = io_in[978:970] == io_idx;
  wire       robIdxMatchSeq_1 = io_in[1012:1004] == io_idx;
  wire       robIdxMatchSeq_2 = io_in[1046:1038] == io_idx;
  wire       robIdxMatchSeq_3 = io_in[1080:1072] == io_idx;
  wire       robIdxMatchSeq_4 = io_in[1114:1106] == io_idx;
  wire       robIdxMatchSeq_5 = io_in[1148:1140] == io_idx;
  wire       robIdxMatchSeq_6 = io_in[1182:1174] == io_idx;
  wire       robIdxMatchSeq_7 = io_in[1216:1208] == io_idx;
  wire       uopCanEnqSeq_0 = uopEnqValidSeq_0 & robIdxMatchSeq_0;
  wire       uopCanEnqSeq_1 = uopEnqValidSeq_1 & robIdxMatchSeq_1;
  wire       uopCanEnqSeq_2 = uopEnqValidSeq_2 & robIdxMatchSeq_2;
  wire       uopCanEnqSeq_3 = uopEnqValidSeq_3 & robIdxMatchSeq_3;
  wire       uopCanEnqSeq_4 = uopEnqValidSeq_4 & robIdxMatchSeq_4;
  wire       uopCanEnqSeq_5 = uopEnqValidSeq_5 & robIdxMatchSeq_5;
  wire       uopCanEnqSeq_6 = uopEnqValidSeq_6 & robIdxMatchSeq_6;
  wire       uopCanEnqSeq_7 = uopEnqValidSeq_7 & robIdxMatchSeq_7;
  wire       instCanEnqSeq_0 = uopEnqValidSeq_0 & io_in[979] & robIdxMatchSeq_0;
  wire       instCanEnqSeq_1 = uopEnqValidSeq_1 & io_in[1013] & robIdxMatchSeq_1;
  wire       instCanEnqSeq_2 = uopEnqValidSeq_2 & io_in[1047] & robIdxMatchSeq_2;
  wire       instCanEnqSeq_3 = uopEnqValidSeq_3 & io_in[1081] & robIdxMatchSeq_3;
  wire       instCanEnqSeq_4 = uopEnqValidSeq_4 & io_in[1115] & robIdxMatchSeq_4;
  wire       instCanEnqSeq_5 = uopEnqValidSeq_5 & io_in[1149] & robIdxMatchSeq_5;
  wire       instCanEnqSeq_6 = uopEnqValidSeq_6 & io_in[1183] & robIdxMatchSeq_6;
  wire [7:0] _instCanEnqFlag_T =
    {instCanEnqSeq_0,
     instCanEnqSeq_1,
     instCanEnqSeq_2,
     instCanEnqSeq_3,
     instCanEnqSeq_4,
     instCanEnqSeq_5,
     instCanEnqSeq_6,
     uopEnqValidSeq_7 & io_in[1217] & robIdxMatchSeq_7};
  wire       isFirstEnq = ~entry_valid & (|_instCanEnqFlag_T);
  wire [3:0] realDestEnqNum =
    {1'h0,
     {1'h0, {1'h0, io_in[969] & uopCanEnqSeq_0} + {1'h0, io_in[1003] & uopCanEnqSeq_1}}
       + {1'h0,
          {1'h0, io_in[1037] & uopCanEnqSeq_2} + {1'h0, io_in[1071] & uopCanEnqSeq_3}}}
    + {1'h0,
       {1'h0, {1'h0, io_in[1105] & uopCanEnqSeq_4} + {1'h0, io_in[1139] & uopCanEnqSeq_5}}
         + {1'h0,
            {1'h0, io_in[1173] & uopCanEnqSeq_6} + {1'h0, io_in[1207] & uopCanEnqSeq_7}}};
  wire [4:0] wbCnt =
    (io_in[483] & io_in[482:474] == io_idx ? io_in[333:329] : 5'h0)
    | (io_in[493] & io_in[492:484] == io_idx ? io_in[338:334] : 5'h0)
    | (io_in[503] & io_in[502:494] == io_idx ? io_in[343:339] : 5'h0)
    | (io_in[513] & io_in[512:504] == io_idx ? io_in[348:344] : 5'h0)
    | (io_in[523] & io_in[522:514] == io_idx ? io_in[353:349] : 5'h0)
    | (io_in[533] & io_in[532:524] == io_idx ? io_in[358:354] : 5'h0)
    | (io_in[543] & io_in[542:534] == io_idx ? io_in[363:359] : 5'h0)
    | (io_in[553] & io_in[552:544] == io_idx ? io_in[368:364] : 5'h0)
    | (io_in[563] & io_in[562:554] == io_idx ? io_in[373:369] : 5'h0)
    | (io_in[573] & io_in[572:564] == io_idx ? io_in[378:374] : 5'h0)
    | (io_in[583] & io_in[582:574] == io_idx ? io_in[383:379] : 5'h0)
    | (io_in[593] & io_in[592:584] == io_idx ? io_in[388:384] : 5'h0)
    | (io_in[603] & io_in[602:594] == io_idx ? io_in[393:389] : 5'h0)
    | (io_in[613] & io_in[612:604] == io_idx ? io_in[398:394] : 5'h0)
    | (io_in[623] & io_in[622:614] == io_idx ? io_in[403:399] : 5'h0)
    | (io_in[633] & io_in[632:624] == io_idx ? io_in[408:404] : 5'h0)
    | (io_in[643] & io_in[642:634] == io_idx ? io_in[413:409] : 5'h0)
    | (io_in[653] & io_in[652:644] == io_idx ? io_in[418:414] : 5'h0)
    | (io_in[663] & io_in[662:654] == io_idx ? io_in[423:419] : 5'h0)
    | (io_in[673] & io_in[672:664] == io_idx ? io_in[428:424] : 5'h0)
    | (io_in[683] & io_in[682:674] == io_idx ? io_in[433:429] : 5'h0)
    | (io_in[693] & io_in[692:684] == io_idx ? io_in[438:434] : 5'h0)
    | (io_in[703] & io_in[702:694] == io_idx ? io_in[443:439] : 5'h0)
    | (io_in[713] & io_in[712:704] == io_idx ? io_in[448:444] : 5'h0)
    | (io_in[723] & io_in[722:714] == io_idx ? io_in[453:449] : 5'h0)
    | (io_in[733] & io_in[732:724] == io_idx ? io_in[458:454] : 5'h0)
    | (io_in[743] & io_in[742:734] == io_idx ? io_in[463:459] : 5'h0)
    | (io_in[753] & io_in[752:744] == io_idx ? io_in[468:464] : 5'h0)
    | (io_in[763] & io_in[762:754] == io_idx ? io_in[473:469] : 5'h0);
  wire       needFlushWriteBack =
    io_in[208] & io_in[207:199] == io_idx & io_in[186] | io_in[218]
    & io_in[217:209] == io_idx & io_in[187] | io_in[228] & io_in[227:219] == io_idx
    & io_in[188] | io_in[238] & io_in[237:229] == io_idx & io_in[189] | io_in[248]
    & io_in[247:239] == io_idx & io_in[190] | io_in[258] & io_in[257:249] == io_idx
    & io_in[191] | io_in[268] & io_in[267:259] == io_idx & io_in[192] | io_in[278]
    & io_in[277:269] == io_idx & io_in[193] | io_in[288] & io_in[287:279] == io_idx
    & io_in[194] | io_in[298] & io_in[297:289] == io_idx & io_in[195] | io_in[308]
    & io_in[307:299] == io_idx & io_in[196] | io_in[318] & io_in[317:309] == io_idx
    & io_in[197] | io_in[328] & io_in[327:319] == io_idx & io_in[198];
  wire [4:0] fflagsRes =
    (io_in[89] & io_in[88:80] == io_idx & io_in[79] ? io_in[78:74] : 5'h0)
    | (io_in[105] & io_in[104:96] == io_idx & io_in[95] ? io_in[94:90] : 5'h0)
    | (io_in[121] & io_in[120:112] == io_idx & io_in[111] ? io_in[110:106] : 5'h0)
    | (io_in[137] & io_in[136:128] == io_idx & io_in[127] ? io_in[126:122] : 5'h0)
    | (io_in[153] & io_in[152:144] == io_idx & io_in[143] ? io_in[142:138] : 5'h0)
    | (io_in[169] & io_in[168:160] == io_idx & io_in[159] ? io_in[158:154] : 5'h0)
    | (io_in[185] & io_in[184:176] == io_idx & io_in[175] ? io_in[174:170] : 5'h0);
  always @(posedge clock) begin
    if (|_enqHit_T) begin
      entry_vls <=
        enqOH_0 & io_in[959] | enqOH_1 & io_in[993] | enqOH_2 & io_in[1027] | enqOH_3
        & io_in[1061] | enqOH_4 & io_in[1095] | enqOH_5 & io_in[1129] | enqOH_6
        & io_in[1163] | enqOH_7 & io_in[1197];
      entry_interrupt_safe <=
        enqOH_0 & io_in[866] | enqOH_1 & io_in[867] | enqOH_2 & io_in[868] | enqOH_3
        & io_in[869] | enqOH_4 & io_in[870] | enqOH_5 & io_in[871] | enqOH_6 & io_in[872]
        | enqOH_7 & io_in[873];
    end
    if (entry_valid & entry_traceBlockInPipe_itype == 4'h4
        & (io_in[9] & io_in[8:0] == io_idx | io_in[19] & io_in[18:10] == io_idx
           | io_in[29] & io_in[28:20] == io_idx))
      entry_traceBlockInPipe_itype <= 4'h5;
    else if (_GEN)
      entry_traceBlockInPipe_itype <=
        (enqOH_0 ? io_in[957:954] : 4'h0) | (enqOH_1 ? io_in[991:988] : 4'h0)
        | (enqOH_2 ? io_in[1025:1022] : 4'h0) | (enqOH_3 ? io_in[1059:1056] : 4'h0)
        | (enqOH_4 ? io_in[1093:1090] : 4'h0) | (enqOH_5 ? io_in[1127:1124] : 4'h0)
        | (enqOH_6 ? io_in[1161:1158] : 4'h0) | (enqOH_7 ? io_in[1195:1192] : 4'h0);
    if (_GEN) begin
      entry_traceBlockInPipe_iretire <=
        (enqOH_0 ? io_in[953:948] : 6'h0) | (enqOH_1 ? io_in[987:982] : 6'h0)
        | (enqOH_2 ? io_in[1021:1016] : 6'h0) | (enqOH_3 ? io_in[1055:1050] : 6'h0)
        | (enqOH_4 ? io_in[1089:1084] : 6'h0) | (enqOH_5 ? io_in[1123:1118] : 6'h0)
        | (enqOH_6 ? io_in[1157:1152] : 6'h0) | (enqOH_7 ? io_in[1191:1186] : 6'h0);
      entry_traceBlockInPipe_ilastsize <=
        enqOH_0 & io_in[947] | enqOH_1 & io_in[981] | enqOH_2 & io_in[1015] | enqOH_3
        & io_in[1049] | enqOH_4 & io_in[1083] | enqOH_5 & io_in[1117] | enqOH_6
        & io_in[1151] | enqOH_7 & io_in[1185];
    end
    entry_fflags <= isFirstEnq ? 5'h0 : {5{|fflagsRes}} & fflagsRes | entry_fflags;
    entry_vxsat <=
      ~isFirstEnq
      & (io_in[40] & io_in[39:31] == io_idx & io_in[30] | io_in[51]
         & io_in[50:42] == io_idx & io_in[41] | io_in[62] & io_in[61:53] == io_idx
         & io_in[52] | io_in[73] & io_in[72:64] == io_idx & io_in[63] | entry_vxsat);
    if (isFirstEnq)
      entry_realDestSize <= realDestEnqNum;
    else if (entry_valid
             & (|{uopCanEnqSeq_0,
                  uopCanEnqSeq_1,
                  uopCanEnqSeq_2,
                  uopCanEnqSeq_3,
                  uopCanEnqSeq_4,
                  uopCanEnqSeq_5,
                  uopCanEnqSeq_6,
                  uopCanEnqSeq_7}))
      entry_realDestSize <= entry_realDestSize + realDestEnqNum;
    if (entry_valid & (entry_needFlush | needFlushWriteBack))
      entry_uopNum <= entry_uopNum - wbCnt;
    else if (~entry_valid & (|_instCanEnqFlag_T))
      entry_uopNum <=
        instCanEnqSeq_0
          ? io_in[964:960]
          : instCanEnqSeq_1
              ? io_in[998:994]
              : instCanEnqSeq_2
                  ? io_in[1032:1028]
                  : instCanEnqSeq_3
                      ? io_in[1066:1062]
                      : instCanEnqSeq_4
                          ? io_in[1100:1096]
                          : instCanEnqSeq_5
                              ? io_in[1134:1130]
                              : instCanEnqSeq_6 ? io_in[1168:1164] : io_in[1202:1198];
    else if (entry_valid)
      entry_uopNum <= entry_uopNum - wbCnt;
    if (entry_valid)
      entry_needFlush <= entry_needFlush | needFlushWriteBack;
    else if (_GEN)
      entry_needFlush <=
        enqOH_0 & io_in[958] | enqOH_1 & io_in[992] | enqOH_2 & io_in[1026] | enqOH_3
        & io_in[1060] | enqOH_4 & io_in[1094] | enqOH_5 & io_in[1128] | enqOH_6
        & io_in[1162] | enqOH_7 & io_in[1196];
  end // always @(posedge)
  wire       _needFlushRedirect_T_4 = io_idx > io_in[863:855];
  wire       _needFlushRedirect_T_5 = io_idx < io_in[854:846];
  always @(posedge clock or posedge reset) begin
    if (reset)
      entry_valid <= 1'h0;
    else
      entry_valid <=
        ~(io_in[844]
          & (io_in[836] & io_in[772:764] == io_idx | io_in[837] & io_in[781:773] == io_idx
             | io_in[838] & io_in[790:782] == io_idx | io_in[839]
             & io_in[799:791] == io_idx | io_in[840] & io_in[808:800] == io_idx
             | io_in[841] & io_in[817:809] == io_idx | io_in[842]
             & io_in[826:818] == io_idx | io_in[843] & io_in[835:827] == io_idx))
        & (_GEN
           | ~(io_in[864]
               & ((io_in[854:846] > io_in[863:855]
                     ? _needFlushRedirect_T_4 & _needFlushRedirect_T_5
                     : _needFlushRedirect_T_4 | _needFlushRedirect_T_5) | io_in[845]))
           & entry_valid);
  end // always @(posedge, posedge)
  `ifdef ENABLE_INITIAL_REG_
    `ifdef FIRRTL_BEFORE_INITIAL
      `FIRRTL_BEFORE_INITIAL
    `endif // FIRRTL_BEFORE_INITIAL
    initial begin
      if (reset)
        entry_valid = 1'h0;
    end // initial
    `ifdef FIRRTL_AFTER_INITIAL
      `FIRRTL_AFTER_INITIAL
    `endif // FIRRTL_AFTER_INITIAL
  `endif // ENABLE_INITIAL_REG_
  assign io_entry =
    {entry_vls,
     entry_interrupt_safe,
     entry_traceBlockInPipe_itype,
     entry_traceBlockInPipe_iretire,
     entry_traceBlockInPipe_ilastsize,
     entry_valid,
     entry_fflags,
     1'h0,
     entry_vxsat,
     entry_realDestSize,
     entry_uopNum,
     entry_needFlush};
endmodule