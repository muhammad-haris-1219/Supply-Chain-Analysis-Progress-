drop DATABASE FinancialDataDB

CREATE DATABASE FinancialDataDB;
use FinancialDataDB

select * from FinancialRawData where organization='ISMAIL' and [pdf-year]=2020 and [statement type]='STATEMENT OF PROFIT OR LOSS'
and [item labels]='Profit after taxation'
;

SELECT * 
FROM FinancialData
WHERE [item labels] NOT LIKE '%[0-9]%'
  AND [item labels] LIKE '%[A-Za-z]%';
   
SELECT Organization, value AS num
FROM FinancialData
CROSS APPLY STRING_SPLIT([Value],' ')
where len(value)>2 

CREATE TABLE FinancialData(
    ID INT PRIMARY KEY,
    Organization VARCHAR(100),
    [Report Year] INT,
    [Statement Type] VARCHAR(100),
    Section VARCHAR(100),
    labels NVARCHAR(MAX),
    [Year] NVARCHAR(50),
    [Values] NVARCHAR(50),
    [PDF-Year] INT,
    [Data Year] INT,
    [Item labels] VARCHAR(250),
    UniqueFinancialID AS (
        CAST([PDF-Year] AS VARCHAR(4)) + '_' + 
        UPPER(LTRIM(RTRIM(Organization))) + '_' + 
        UPPER(LTRIM(RTRIM([Statement Type]))) + '_' + 
        CAST([Data Year] AS VARCHAR(4)) + '_' + 
        UPPER(LTRIM(RTRIM([Item labels])))
    ) PERSISTED
);






INSERT INTO FinancialData (Organization, Statemnet, [Sub-Section], labels, [year], [values])
SELECT
    OrganizationName,
    StatementName,
    SubSectionHeader,
    LineItemLabel,
    ReportingYear,
    value AS [values]
FROM FinancialStatements
CROSS APPLY STRING_SPLIT(ValuesArray, ' ')
WHERE LineItemLabel NOT LIKE '%[0-9]%'
  AND LineItemLabel LIKE '%[A-Za-z]%'

  





