# Patient-Led Experimentation With GLP-1 Receptor Agonists: Social Media Analysis of Unmonitored Dosing and Medication Modification Behaviours

**Authors:** Poornima Velswamy¹†, Alexandar Vincet-paulraj†, Lauren E Walker*  
**Affiliations:** ¹ Centre for Experimental Therapeutics (TherEx), University of Liverpool, Liverpool, United Kingdom.  
*† The authors have contributed equally to this work.*  
**Repository:** [https://github.com/alxv/Social-Media-Analysis-of-Weight-loss-Mediction](https://github.com/alxv/Social-Media-Analysis-of-Weight-loss-Mediction)

---

## Overview
This repository contains the code, datasets, and analysis notebooks for the publication: **"Patient-Led Experimentation With GLP-1 Receptor Agonists: Social Media Analysis of Unmonitored Dosing and Medication Modification Behaviours."** 

The study investigates the unmonitored dosing, compounding, and modification of GLP-1 receptor agonists (e.g., semaglutide, tirzepatide) discussed on social media platforms like Reddit. This repository specifically houses the tools used to download and analyze related pharmacovigilance data from the FDA Adverse Event Reporting System (FAERS), conduct Proportional Reporting Ratio (PRR) signal detection, and compare these official adverse event signals to Reddit-derived social media timelines for early detection analysis.

## Repository Structure

```text
├── Weight_Loss_Meds_FAERS_Analysis.ipynb  # Jupyter notebook containing the core data analysis, PRR calculations, and timeline visualizations
├── download_faers_wl.py                   # Python script used to fetch and process historical FAERS data
├── weight_loss_drug_list.csv              # Input dataset containing the specific medications and variants analyzed
└── README.md                              # Project documentation
