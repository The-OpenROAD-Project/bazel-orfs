| arm | f | core-only P | of which clock | core-only dynamic / iteration | leakage / iteration | CoreMark/MHz |
|---|---|---|---|---|---|---|
| grt, 1282 ps | 780 MHz | 7.80 mW | 2.96 mW | **4.07 µJ** | 1.04 nJ | 2.45 |
| synth, 1282 ps | 780 MHz | 2.50 mW | 0.14 mW | **1.30 µJ** | 1.04 nJ | 2.45 |
| synth, 1282 ps, 20 ps clock slew | 780 MHz | 2.50 mW | 0.14 mW | **1.30 µJ** | 1.04 nJ | 2.45 |
| synth, 2000 ps | 500 MHz | 1.96 mW | 0.14 mW | **1.60 µJ** | 1.63 nJ | 2.45 |
| synth, 2000 ps, 20 ps clock slew | 500 MHz | 1.94 mW | 0.14 mW | **1.58 µJ** | 1.63 nJ | 2.45 |
| synth, 10000 ps | 100 MHz | 0.59 mW | 0.06 mW | **2.40 µJ** | 8.15 nJ | 2.45 |
| synth, 10000 ps, 20 ps clock slew | 100 MHz | 0.58 mW | 0.06 mW | **2.36 µJ** | 8.15 nJ | 2.45 |
| [15] synth, 100 MHz | 100 MHz | — | none | **3.40 µJ** | 0.75 nJ | 2.36 |
| [15] synth, 500 MHz | 500 MHz | — | none | **0.92 µJ** | 5.54 nJ | 2.36 |

Core-only is report_power's Total minus its Macro group. One iteration is 407,448 cycles; energy is power times cycles times the SDC period.
