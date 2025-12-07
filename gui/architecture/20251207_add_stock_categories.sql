BEGIN;

-- Insert normalized categories (idempotent)
INSERT INTO public.stock_categories (name, description)
VALUES
  ('Mining & Commodities', 'From architecture/categories.txt'),
  ('General Retail', 'From architecture/categories.txt'),
  ('Banks & Financial Services', 'From architecture/categories.txt'),
  ('Property / REITs', 'From architecture/categories.txt'),
  ('Investment Holding Companies', 'From architecture/categories.txt'),
  ('Telecommunications', 'From architecture/categories.txt'),
  ('Insurance (Life & General)', 'From architecture/categories.txt'),
  ('Logistics & Transport', 'From architecture/categories.txt'),
  ('Construction & Materials', 'From architecture/categories.txt'),
  ('Small/Mid-Cap Industrials', 'From architecture/categories.txt'),
  ('Healthcare & Hospitals', 'From architecture/categories.txt'),
  ('Agriculture & Poultry', 'From architecture/categories.txt'),
  ('AltX / Speculative / Penny Stocks', 'From architecture/categories.txt')
ON CONFLICT DO NOTHING;

-- Backfill tickers per category
-- 1) Mining & Commodities
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Mining & Commodities')
WHERE ticker IN ('ACL.JO','AGL.JO','ANG.JO','APH.JO','ARI.JO','BHG.JO','DRD.JO','EPS.JO','EUZ.JO','EXX.JO','GFI.JO','GLN.JO','GML.JO','HAR.JO','IMP.JO','JBL.JO','KIO.JO','KP2.JO','MCZ.JO','MKR.JO','MNP.JO','MRF.JO','NPH.JO','OAO.JO','ORN.JO','PAN.JO','S32.JO','SAP.JO','SDL.JO','SKA.JO','SLG.JO','SOL.JO','SSW.JO','TGA.JO','THA.JO','VAL.JO','WEZ.JO');

-- 2) General Retail
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'General Retail')
WHERE ticker IN ('BOX.JO','CFR.JO','CHP.JO','CLS.JO','CMH.JO','CSB.JO','DCP.JO','ITE.JO','LEW.JO','MRP.JO','MTH.JO','PIK.JO','PPH.JO','SHP.JO','SPP.JO','TFG.JO','TRU.JO','WBC.JO','WHL.JO');

-- 3) Banks & Financial Services
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Banks & Financial Services')
WHERE ticker IN ('ABG.JO','AFH.JO','CML.JO','CPI.JO','FGL.JO','FSR.JO','INL.JO','INP.JO','JSE.JO','KST.JO','LSK.JO','N91.JO','NED.JO','NTU.JO','NY1.JO','PPE.JO','QLT.JO','SBK.JO','SBPP.JO','SYG.JO','VUN.JO','WVR.JO');

-- 4) Property / REITs
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Property / REITs')
WHERE ticker IN ('ANI.JO','APF.JO','ATT.JO','BTN.JO','CPP.JO','CVW.JO','DLT.JO','EMI.JO','EQU.JO','EXP.JO','FFB.JO','FTA.JO','FTB.JO','GRT.JO','GTC.JO','HET.JO','HMN.JO','HYP.JO','LTE.JO','MSP.JO','NRL.JO','NRP.JO','OAS.JO','OCT.JO','PHP.JO','PPR.JO','RDF.JO','RES.JO','SAC.JO','SAR.JO','SEA.JO','SHC.JO','SRE.JO','SRI.JO','SSS.JO','TEX.JO','VIS.JO','VKE.JO');

-- 5) Investment Holding Companies
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Investment Holding Companies')
WHERE ticker IN ('AOO.JO','ARA.JO','BAT.JO','BRT.JO','DNB.JO','EPE.JO','GPL.JO','GRSP.JO','HCI.JO','MTNZF.JO','NPN.JO','PRX.JO','REM.JO','RMH.JO','RNI.JO','SBP.JO','SZK.JO','UPL.JO','ZED.JO');

-- 6) Telecommunications
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Telecommunications')
WHERE ticker IN ('BLU.JO','MTN.JO','TKG.JO','VOD.JO');

-- 7) Insurance (Life & General)
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Insurance (Life & General)')
WHERE ticker IN ('CLI.JO','DSY.JO','MTM.JO','OMU.JO','OUT.JO','SLM.JO','SNT.JO');

-- 8) Logistics & Transport
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Logistics & Transport')
WHERE ticker IN ('BAW.JO','GND.JO','GNDP.JO','MMP.JO','PWR.JO','SNV.JO','SPG.JO','ZZD.JO');

-- 9) Construction & Materials
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Construction & Materials')
WHERE ticker IN ('AEG.JO','AFT.JO','CAC.JO','CGR.JO','MDI.JO','PPC.JO','RBX.JO','SEP.JO','SSK.JO','TRL.JO','WBO.JO');

-- 10) Small/Mid-Cap Industrials
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Small/Mid-Cap Industrials')
WHERE ticker IN ('ADH.JO','ADR.JO','AEL.JO','AFE.JO','ANH.JO','ART.JO','AVI.JO','BCF.JO','BEL.JO','BID.JO','BTI.JO','BVT.JO','BYI.JO','CAA.JO','CAT.JO','CLH.JO','COH.JO','DTC.JO','ENX.JO','FBR.JO','HDC.JO','HLM.JO','IOC.JO','ISB.JO','IVT.JO','KAP.JO','KRO.JO','LBR.JO','MFL.JO','MPT.JO','MST.JO','MTA.JO','NPK.JO','NVS.JO','NWL.JO','OMN.JO','OPA.JO','PBT.JO','PMR.JO','PMV.JO','RFG.JO','RLO.JO','RTO.JO','SDO.JO','SOH.JO','SSU.JO','SUI.JO','SUR.JO','TBS.JO','TPC.JO','TSG.JO');

-- 11) Healthcare & Hospitals
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Healthcare & Hospitals')
WHERE ticker IN ('ACT.JO','APN.JO','LHC.JO','NTC.JO','RHB.JO');

-- 12) Agriculture & Poultry
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'Agriculture & Poultry')
WHERE ticker IN ('ARL.JO','CKS.JO','KAL.JO','OCE.JO','QFH.JO','RBO.JO','RCL.JO','SHG.JO','YRK.JO');

-- 13) AltX / Speculative / Penny Stocks
UPDATE public.stock_details
SET stock_category_id = (SELECT category_id FROM public.stock_categories WHERE name = 'AltX / Speculative / Penny Stocks')
WHERE ticker IN ('4SI.JO','AXX.JO','CCC.JO','ISA.JO','LAB.JO','MTU.JO','REN.JO','RNG.JO','TLM.JO','XII.JO');

COMMIT;
