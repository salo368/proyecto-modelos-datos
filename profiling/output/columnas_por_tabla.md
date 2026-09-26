
## Base de datos: classicmodels

### Tabla: customers

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| customerNumber | int(11) | NO | PK |  |
| customerName | varchar(50) | NO |  |  |
| contactLastName | varchar(50) | NO |  |  |
| contactFirstName | varchar(50) | NO |  |  |
| phone | varchar(50) | NO |  |  |
| addressLine1 | varchar(50) | NO |  |  |
| addressLine2 | varchar(50) | YES |  |  |
| city | varchar(50) | NO |  |  |
| state | varchar(50) | YES |  |  |
| postalCode | varchar(15) | YES |  |  |
| country | varchar(50) | NO |  |  |
| salesRepEmployeeNumber | int(11) | YES |  | FK -> employees.employeeNumber |
| creditLimit | decimal(10,2) | YES |  |  |

**Llave primaria:** customerNumber

### Tabla: employees

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| employeeNumber | int(11) | NO | PK |  |
| lastName | varchar(50) | NO |  |  |
| firstName | varchar(50) | NO |  |  |
| extension | varchar(10) | NO |  |  |
| email | varchar(100) | NO |  |  |
| officeCode | varchar(10) | NO |  | FK -> offices.officeCode |
| reportsTo | int(11) | YES |  | FK -> employees.employeeNumber |
| jobTitle | varchar(50) | NO |  |  |

**Llave primaria:** employeeNumber

### Tabla: offices

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| officeCode | varchar(10) | NO | PK |  |
| city | varchar(50) | NO |  |  |
| phone | varchar(50) | NO |  |  |
| addressLine1 | varchar(50) | NO |  |  |
| addressLine2 | varchar(50) | YES |  |  |
| state | varchar(50) | YES |  |  |
| country | varchar(50) | NO |  |  |
| postalCode | varchar(15) | NO |  |  |
| territory | varchar(10) | NO |  |  |

**Llave primaria:** officeCode

### Tabla: orderdetails

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| orderNumber | int(11) | NO | PK | FK -> orders.orderNumber |
| productCode | varchar(15) | NO | PK | FK -> products.productCode |
| quantityOrdered | int(11) | NO |  |  |
| priceEach | decimal(10,2) | NO |  |  |
| orderLineNumber | smallint(6) | NO |  |  |

**Llave primaria:** orderNumber, productCode

### Tabla: orders

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| orderNumber | int(11) | NO | PK |  |
| orderDate | date | NO |  |  |
| requiredDate | date | NO |  |  |
| shippedDate | date | YES |  |  |
| status | varchar(15) | NO |  |  |
| comments | text | YES |  |  |
| customerNumber | int(11) | NO |  | FK -> customers.customerNumber |

**Llave primaria:** orderNumber

### Tabla: payments

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| customerNumber | int(11) | NO | PK | FK -> customers.customerNumber |
| checkNumber | varchar(50) | NO | PK |  |
| paymentDate | date | NO |  |  |
| amount | decimal(10,2) | NO |  |  |

**Llave primaria:** customerNumber, checkNumber

### Tabla: productlines

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| productLine | varchar(50) | NO | PK |  |
| textDescription | varchar(4000) | YES |  |  |
| htmlDescription | mediumtext | YES |  |  |
| image | mediumblob | YES |  |  |

**Llave primaria:** productLine

### Tabla: products

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| productCode | varchar(15) | NO | PK |  |
| productName | varchar(70) | NO |  |  |
| productLine | varchar(50) | NO |  | FK -> productlines.productLine |
| productScale | varchar(10) | NO |  |  |
| productVendor | varchar(50) | NO |  |  |
| productDescription | text | NO |  |  |
| quantityInStock | smallint(6) | NO |  |  |
| buyPrice | decimal(10,2) | NO |  |  |
| MSRP | decimal(10,2) | NO |  |  |

**Llave primaria:** productCode


## Base de datos: customerservice

### Tabla: cs_customer_calls

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| employeenumber | integer | NO |  | FK -> cs_employees.employeenumber |
| customernumber | integer | NO |  | FK -> cs_customers.customernumber |
| productcode | character varying(15) | NO |  | FK -> cs_products.productcode |
| text | character varying(200) | YES |  |  |
| date | timestamp(6) without time zone | NO |  |  |

**Llave primaria:** (ninguna definida)

### Tabla: cs_customer_products

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| customernumber | integer | NO | PK | FK -> cs_customers.customernumber |
| productcode | character varying(15) | NO | PK | FK -> cs_products.productcode |

**Llave primaria:** customernumber, productcode

### Tabla: cs_customers

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| customernumber | integer | NO | PK |  |
| contactlastname | character varying(50) | YES |  |  |
| contactfirstname | character varying(50) | YES |  |  |
| phone | character varying(50) | YES |  |  |
| addressline1 | character varying(50) | YES |  |  |
| addressline2 | character varying(50) | YES |  |  |
| city | character varying(50) | YES |  |  |
| state | character varying(50) | YES |  |  |
| postalcode | character varying(15) | YES |  |  |
| country | character varying(50) | YES |  |  |

**Llave primaria:** customernumber

### Tabla: cs_employees

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| employeenumber | integer | NO | PK |  |
| lastname | character varying(50) | YES |  |  |
| firstname | character varying(50) | YES |  |  |
| email | character varying(100) | YES |  |  |

**Llave primaria:** employeenumber

### Tabla: cs_products

| Columna | Tipo de dato | Nulo | PK | FK -> referencia |
|---|---|---|---|---|
| productcode | character varying(15) | NO | PK |  |
| productname | character varying(70) | YES |  |  |
| productscale | character varying(10) | YES |  |  |
| productvendor | character varying(50) | YES |  |  |
| productdescription | text | YES |  |  |

**Llave primaria:** productcode
