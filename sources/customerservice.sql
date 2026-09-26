--
-- PostgreSQL database dump
--

-- Dumped from database version 13.1
-- Dumped by pg_dump version 13.1

-- Started on 2021-02-09 20:48:26

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 204 (class 1259 OID 16434)
-- Name: cs_customer_calls; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cs_customer_calls (
    employeenumber integer NOT NULL,
    customernumber integer NOT NULL,
    productcode character varying(15) NOT NULL,
    text character varying(200),
    date timestamp(6) without time zone NOT NULL
);


ALTER TABLE public.cs_customer_calls OWNER TO postgres;

--
-- TOC entry 203 (class 1259 OID 16419)
-- Name: cs_customer_products; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cs_customer_products (
    customernumber integer NOT NULL,
    productcode character varying(15) NOT NULL
);


ALTER TABLE public.cs_customer_products OWNER TO postgres;

--
-- TOC entry 200 (class 1259 OID 16398)
-- Name: cs_customers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cs_customers (
    customernumber integer NOT NULL,
    contactlastname character varying(50),
    contactfirstname character varying(50),
    phone character varying(50),
    addressline1 character varying(50),
    addressline2 character varying(50),
    city character varying(50),
    state character varying(50),
    postalcode character varying(15),
    country character varying(50)
);


ALTER TABLE public.cs_customers OWNER TO postgres;

--
-- TOC entry 202 (class 1259 OID 16414)
-- Name: cs_employees; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cs_employees (
    employeenumber integer NOT NULL,
    lastname character varying(50),
    firstname character varying(50),
    email character varying(100)
);


ALTER TABLE public.cs_employees OWNER TO postgres;

--
-- TOC entry 201 (class 1259 OID 16404)
-- Name: cs_products; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cs_products (
    productcode character varying(15) NOT NULL,
    productname character varying(70),
    productscale character varying(10),
    productvendor character varying(50),
    productdescription text
);


ALTER TABLE public.cs_products OWNER TO postgres;

--
-- TOC entry 3012 (class 0 OID 16434)
-- Dependencies: 204
-- Data for Name: cs_customer_calls; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cs_customer_calls (employeenumber, customernumber, productcode, text, date) FROM stdin;
26	145	S50_1341	Cras laoreet leo et massa rhoncus id posuere enim varius.	2005-05-09 00:00:00
26	303	S24_2972	Curabitur hendrerit orci et vestibulum rhoncus.	2003-08-06 00:00:00
26	386	S24_3151	In ut ex nec arcu ultricies dictum.	2003-06-25 00:00:00
27	259	S24_1628	Nullam et purus eleifend laoreet mauris et dapibus tortor.	2004-08-15 00:00:00
27	276	S24_1578	Cras rhoncus ante sit amet iaculis consequat.	2004-09-30 00:00:00
27	357	S50_1514	Aenean in elit iaculis tortor blandit eleifend sed at diam.	2004-08-24 00:00:00
28	114	S18_2432	Ut pulvinar massa ultrices tortor viverra id dictum purus malesuada.	2004-10-29 00:00:00
28	124	S18_2625	Etiam luctus massa ac nibh lobortis rutrum.	2004-01-25 00:00:00
28	276	S32_4289	Ut posuere magna ut est gravida dictum.	2003-04-26 00:00:00
28	324	S50_1341	Vestibulum sed diam hendrerit magna volutpat volutpat.	2003-04-11 00:00:00
28	357	S50_1514	Cras lacinia erat venenatis erat tempus ac posuere arcu dictum.	2004-02-12 00:00:00
29	145	S50_1341	Integer vulputate ipsum eu eros eleifend sollicitudin.	2003-09-02 00:00:00
29	157	S32_3207	Ut eu metus sit amet diam porta tincidunt.	2003-04-27 00:00:00
29	282	S24_2887	Praesent ultricies ex id nisl posuere aliquet.	2004-09-28 00:00:00
29	386	S24_3151	Mauris aliquet orci in dictum iaculis.	2003-06-14 00:00:00
29	452	S700_1691	Sed ultrices velit mollis dui tempor eu eleifend tortor congue.	2003-12-02 00:00:00
30	112	S10_4757	Quisque sed arcu vel turpis egestas consequat fringilla et odio.	2004-02-26 00:00:00
30	168	S18_2325	Donec vel ligula id nibh faucibus maximus.	2005-02-27 00:00:00
30	363	S32_4485	Praesent id eros eleifend suscipit tellus et finibus nibh.	2003-09-17 00:00:00
30	424	S18_2957	Lorem ipsum dolor sit amet consectetur adipiscing elit.	2003-02-19 00:00:00
30	456	S18_4522	Etiam tempor purus quis scelerisque elementum.	2004-01-09 00:00:00
1	198	S18_2325	Vestibulum a dolor sed sapien ultricies luctus.	2004-11-15 00:00:00
2	114	S18_2432	Vestibulum vitae ante id odio cursus pellentesque ac in lectus.	2004-11-01 00:00:00
2	233	S72_3212	Morbi feugiat nisl euismod mi faucibus vitae aliquam tellus euismod.	2003-08-15 00:00:00
2	311	S50_4713	Duis id dolor faucibus pharetra risus ut pretium velit.	2003-11-23 00:00:00
3	363	S18_3856	Donec id risus id orci blandit sodales nec vitae eros.	2005-02-20 00:00:00
4	204	S18_4668	Mauris sed felis quis ex pretium porttitor.	2003-09-30 00:00:00
4	276	S24_1578	In dictum erat non aliquam ultricies.	2004-01-28 00:00:00
4	282	S24_2887	Mauris bibendum sapien non est dictum ac imperdiet sem hendrerit.	2003-09-30 00:00:00
4	311	S50_4713	Maecenas cursus arcu quis purus hendrerit laoreet.	2004-10-26 00:00:00
4	321	S24_2000	Suspendisse accumsan eros quis magna pretium luctus.	2004-10-28 00:00:00
5	112	S10_4757	Aenean sollicitudin risus nec ligula consequat maximus.	2004-07-30 00:00:00
5	177	S12_3380	Proin vehicula magna in lorem dapibus vehicula.	2004-01-07 00:00:00
5	477	S700_1691	Proin id est ut tellus pellentesque interdum.	2004-08-17 00:00:00
5	496	S24_1628	Suspendisse a leo malesuada lobortis tellus mollis cursus elit.	2004-11-22 00:00:00
6	250	S700_3962	Maecenas eu eros ac sapien tincidunt vulputate.	2004-03-06 00:00:00
6	278	S72_1253	Mauris commodo magna eget congue euismod.	2004-10-31 00:00:00
6	386	S24_3151	Donec in leo vel risus tempus varius.	2004-03-19 00:00:00
7	151	S18_4933	Vivamus sed neque ut diam aliquet feugiat.	2003-10-05 00:00:00
7	357	S50_1514	Mauris laoreet sem non ornare dapibus.	2004-06-04 00:00:00
8	128	S700_2047	Nulla in quam in ligula maximus mattis.	2004-08-05 00:00:00
8	167	S700_3505	Integer porttitor ligula et quam faucibus pellentesque.	2003-08-24 00:00:00
8	376	S50_1514	Quisque aliquet tortor quis magna pretium hendrerit.	2004-11-29 00:00:00
8	382	S32_4485	In eget tortor quis augue fermentum ultricies at ut ligula.	2004-06-25 00:00:00
9	112	S10_4757	Cras tristique metus id purus sodales venenatis.	2003-07-03 00:00:00
9	167	S700_3505	Quisque et ipsum ultrices pulvinar ex in imperdiet lorem.	2005-04-29 00:00:00
9	311	S50_4713	Vivamus scelerisque erat at convallis porta.	2004-02-10 00:00:00
9	362	S700_1938	Suspendisse eu mauris hendrerit sem congue imperdiet vitae laoreet nibh.	2003-09-07 00:00:00
9	382	S32_4485	Fusce id ligula gravida consectetur nunc at ultrices neque.	2003-09-27 00:00:00
9	477	S700_1691	Ut volutpat diam ac dolor dignissim sit amet convallis felis ornare.	2003-09-17 00:00:00
10	204	S18_4668	Nam efficitur turpis at sagittis mattis.	2004-07-01 00:00:00
10	314	S32_3522	Vivamus fermentum magna a tortor tempor vitae molestie nunc suscipit.	2004-02-09 00:00:00
11	314	S18_1749	Nulla eget nunc et libero lacinia porta.	2003-11-06 00:00:00
11	323	S24_2000	In sit amet risus consectetur mattis mi at iaculis felis.	2003-03-20 00:00:00
11	424	S18_2957	Aenean bibendum diam a leo suscipit eget venenatis ex gravida.	2004-03-01 00:00:00
11	471	S24_4048	Morbi in lorem eu velit pellentesque aliquam a et odio.	2004-02-25 00:00:00
12	172	S10_4698	Aenean ac tellus id sem consequat maximus id sed quam.	2003-08-11 00:00:00
12	240	S24_3151	Aliquam in mi vel nisl fringilla varius vel ut sem.	2003-12-09 00:00:00
12	363	S32_4485	Duis ornare mauris id nulla egestas vel congue urna ornare.	2003-04-11 00:00:00
12	363	S50_1392	Nullam in sem ornare tincidunt purus in cursus ipsum.	2003-03-07 00:00:00
12	465	S18_3140	Nullam a ipsum ornare volutpat ligula sit amet tincidunt augue.	2004-05-29 00:00:00
13	219	S18_1129	Morbi in mauris lacinia mattis elit nec aliquet nisl.	2003-11-30 00:00:00
13	357	S50_1514	Vivamus vel nisi eget purus tincidunt cursus.	2004-05-25 00:00:00
13	452	S700_1691	Maecenas mattis nulla at aliquam consectetur.	2003-09-14 00:00:00
14	157	S32_3207	Curabitur eget enim eget lacus mattis sollicitudin eu et velit.	2003-10-14 00:00:00
15	151	S18_4933	Vestibulum a augue condimentum commodo mauris ut lacinia magna.	2004-10-23 00:00:00
15	496	S24_1628	In non eros eu quam bibendum tempor.	2004-04-13 00:00:00
16	223	S18_1749	Maecenas egestas quam at nibh sodales congue.	2004-03-11 00:00:00
16	276	S32_4289	Phasellus nec tortor a arcu fringilla molestie.	2004-04-06 00:00:00
16	386	S24_3151	Pellentesque rhoncus nunc at sem blandit mollis.	2004-04-16 00:00:00
16	443	S18_2581	Aenean a sapien suscipit rhoncus odio nec condimentum nisi.	2003-07-06 00:00:00
16	465	S18_3320	In non ipsum quis dui pretium hendrerit.	2005-04-05 00:00:00
17	307	S18_1342	Duis ac est at nulla ullamcorper facilisis eget sed tellus.	2005-02-14 00:00:00
17	319	S18_1129	Proin ac quam ut odio mattis dapibus eu vitae leo.	2003-08-18 00:00:00
17	363	S18_3856	Sed laoreet metus sed varius maximus.	2005-01-16 00:00:00
18	172	S18_2325	Suspendisse vel ante sollicitudin viverra orci nec auctor felis.	2004-08-02 00:00:00
18	177	S12_3380	Phasellus efficitur lorem vitae erat venenatis sit amet auctor lectus suscipit.	2005-02-12 00:00:00
18	303	S24_3432	Nam a libero semper massa sollicitudin dignissim eleifend eu tellus.	2003-10-30 00:00:00
18	314	S32_3522	Nullam ultricies dui quis enim dictum a placerat libero posuere.	2004-11-28 00:00:00
18	361	S24_2360	Vestibulum lobortis metus ut felis rutrum tempus.	2004-02-11 00:00:00
18	450	S18_4027	Morbi rutrum justo id sodales varius.	2004-10-12 00:00:00
18	477	S700_1691	Proin ac sem vulputate vestibulum magna sed eleifend justo.	2004-09-14 00:00:00
19	128	S700_2047	Mauris cursus metus sed mi porta venenatis.	2004-01-13 00:00:00
19	144	S18_3140	Nulla nec leo non dolor lacinia vehicula at in elit.	2004-08-04 00:00:00
19	211	S18_2625	Donec nec ex commodo maximus orci sed convallis arcu.	2003-09-15 00:00:00
19	276	S32_4289	Etiam sed risus fermentum dui varius imperdiet.	2004-09-27 00:00:00
19	412	S24_2840	Cras vel magna id eros varius scelerisque non vel mauris.	2003-05-15 00:00:00
20	144	S18_3140	Ut volutpat velit at mattis suscipit.	2004-06-19 00:00:00
20	166	S24_1937	Integer et tellus ut eros viverra pellentesque.	2003-08-24 00:00:00
20	321	S24_2011	Nullam in lacus ornare condimentum enim nec tempor odio.	2003-10-13 00:00:00
21	148	S50_4713	Nunc vel erat vitae ante suscipit cursus sit amet a nisi.	2004-04-18 00:00:00
21	167	S700_3505	Donec congue tellus sed arcu iaculis posuere.	2005-01-03 00:00:00
21	177	S12_3380	Nunc a mauris vel velit tincidunt auctor.	2004-10-02 00:00:00
21	356	S700_1691	Sed et orci eu sem posuere tempor.	2004-11-01 00:00:00
21	456	S18_4522	In ac elit quis felis pellentesque faucibus at quis ipsum.	2004-08-30 00:00:00
21	477	S700_1691	Quisque condimentum ligula venenatis feugiat malesuada.	2004-03-12 00:00:00
22	311	S50_4713	Suspendisse efficitur purus et leo mattis eu porttitor magna lobortis.	2003-06-04 00:00:00
22	376	S50_1514	Maecenas quis purus quis felis sollicitudin finibus eu eu mauris.	2003-03-03 00:00:00
22	465	S18_3140	Nam dictum lacus ut malesuada tempor.	2004-07-01 00:00:00
23	131	S700_2047	Vivamus ac augue et arcu placerat ultricies volutpat vitae massa.	2004-04-06 00:00:00
23	319	S18_3259	Maecenas aliquam est nec porta scelerisque.	2004-09-25 00:00:00
23	412	S24_2840	Proin facilisis odio sit amet nibh scelerisque non posuere turpis maximus.	2004-07-29 00:00:00
24	412	S24_2840	In scelerisque ligula quis erat iaculis eget facilisis sem consequat.	2004-06-19 00:00:00
24	462	S32_4289	Quisque malesuada ante eget tortor facilisis vel cursus magna vulputate.	2005-03-04 00:00:00
25	114	S18_2432	Suspendisse in quam sed sapien semper lacinia.	2004-03-16 00:00:00
25	424	S18_2957	Curabitur non ex vitae enim sollicitudin eleifend.	2004-06-14 00:00:00
25	443	S18_2581	Duis quis libero nec lorem scelerisque vestibulum quis vitae arcu.	2004-02-02 00:00:00
25	443	S24_2841	Maecenas posuere elit sit amet eros aliquam rhoncus.	2003-05-06 00:00:00
\.


--
-- TOC entry 3011 (class 0 OID 16419)
-- Dependencies: 203
-- Data for Name: cs_customer_products; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cs_customer_products (customernumber, productcode) FROM stdin;
112	S10_4757
114	S18_2432
114	S18_3782
124	S18_2625
128	S700_2047
129	S10_2016
131	S700_2047
144	S18_3140
145	S50_1341
145	S72_3212
148	S50_4713
151	S18_4933
157	S32_3207
166	S24_1937
166	S32_3207
167	S700_3505
168	S18_2325
171	S700_3167
172	S10_4698
172	S18_2325
172	S700_2047
177	S12_3380
177	S700_2834
187	S18_2581
189	S700_1691
198	S18_2325
204	S18_4668
206	S18_3782
209	S18_3278
209	S18_3856
211	S18_2625
216	S24_2972
219	S18_1129
223	S18_1749
227	S18_1889
233	S72_3212
240	S24_3151
240	S24_4258
247	S50_1514
250	S700_3962
259	S24_1628
276	S24_1578
276	S32_4289
278	S72_1253
282	S24_2887
298	S12_3380
303	S24_2972
303	S24_3432
307	S18_1342
311	S50_4713
314	S18_1749
314	S32_3522
319	S18_1129
319	S18_3259
319	S700_1938
321	S24_2000
321	S24_2011
323	S24_2000
324	S50_1341
328	S18_2319
333	S18_2795
339	S18_1589
344	S18_4668
353	S24_3969
353	S50_1514
356	S700_1691
357	S50_1514
357	S700_2610
361	S24_2360
362	S700_1938
363	S18_3856
363	S32_4485
363	S50_1392
376	S50_1514
382	S24_4278
382	S32_4485
385	S12_3148
385	S18_3136
386	S24_3151
412	S24_2840
424	S18_2957
443	S18_2581
443	S24_2000
443	S24_2841
450	S18_4027
452	S700_1691
452	S700_3505
456	S18_4522
456	S72_1253
462	S32_4289
465	S18_3140
465	S18_3320
471	S24_2022
471	S24_4048
473	S18_3856
475	S18_2625
477	S700_1691
481	S32_2509
484	S32_3207
487	S18_1342
496	S24_1628
\.


--
-- TOC entry 3008 (class 0 OID 16398)
-- Dependencies: 200
-- Data for Name: cs_customers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cs_customers (customernumber, contactlastname, contactfirstname, phone, addressline1, addressline2, city, state, postalcode, country) FROM stdin;
103	Schmitt	Carine 	40.32.2555	54, rue Royale	\N	Nantes	\N	44000	France
112	King	Jean	7025551838	8489 Strong St.	\N	Las Vegas	NV	83030	USA
114	Ferguson	Peter	03 9520 4555	636 St Kilda Road	Level 3	Melbourne	Victoria	3004	Australia
119	Labrune	Janine 	40.67.8555	67, rue des Cinquante Otages	\N	Nantes	\N	44000	France
121	Bergulfsen	Jonas 	07-98 9555	Erling Skakkes gate 78	\N	Stavern	\N	4110	Norway
124	Nelson	Susan	4155551450	5677 Strong St.	\N	San Rafael	CA	97562	USA
125	Piestrzeniewicz	Zbyszek 	(26) 642-7555	ul. Filtrowa 68	\N	Warszawa	\N	01-012	Poland
128	Keitel	Roland	+49 69 66 90 2555	Lyonerstr. 34	\N	Frankfurt	\N	60528	Germany
129	Murphy	Julie	6505555787	5557 North Pendale Street	\N	San Francisco	CA	94217	USA
131	Lee	Kwai	2125557818	897 Long Airport Avenue	\N	NYC	NY	10022	USA
141	Freyre	Diego 	(91) 555 94 44	C/ Moralzarzal, 86	\N	Madrid	\N	28034	Spain
144	Berglund	Christina 	0921-12 3555	Berguvsvägen  8	\N	Luleå	\N	S-958 22	Sweden
145	Petersen	Jytte 	31 12 3555	Vinbæltet 34	\N	Kobenhavn	\N	1734	Denmark
146	Saveley	Mary 	78.32.5555	2, rue du Commerce	\N	Lyon	\N	69004	France
148	Natividad	Eric	+65 221 7555	Bronz Sok.	Bronz Apt. 3/6 Tesvikiye	Singapore	\N	079903	Singapore
151	Young	Jeff	2125557413	4092 Furth Circle	Suite 400	NYC	NY	10022	USA
157	Leong	Kelvin	2155551555	7586 Pompton St.	\N	Allentown	PA	70267	USA
161	Hashimoto	Juri	6505556809	9408 Furth Circle	\N	Burlingame	CA	94217	USA
166	Victorino	Wendy	+65 224 1555	106 Linden Road Sandown	2nd Floor	Singapore	\N	069045	Singapore
167	Oeztan	Veysel	+47 2267 3215	Brehmen St. 121	PR 334 Sentrum	Bergen	\N	N 5804	Norway  
168	Franco	Keith	2035557845	149 Spinnaker Dr.	Suite 101	New Haven	CT	97823	USA
169	de Castro	Isabel 	(1) 356-5555	Estrada da saúde n. 58	\N	Lisboa	\N	1756	Portugal
171	Rancé	Martine 	20.16.1555	184, chaussée de Tournai	\N	Lille	\N	59000	France
172	Bertrand	Marie	(1) 42.34.2555	265, boulevard Charonne	\N	Paris	\N	75012	France
173	Tseng	Jerry	6175555555	4658 Baden Av.	\N	Cambridge	MA	51247	USA
175	King	Julie	2035552570	25593 South Bay Ln.	\N	Bridgewater	CT	97562	USA
177	Kentary	Mory	+81 06 6342 5555	1-6-20 Dojima	\N	Kita-ku	Osaka	 530-0003	Japan
181	Frick	Michael	2125551500	2678 Kingston Rd.	Suite 101	NYC	NY	10022	USA
186	Karttunen	Matti	90-224 8555	Keskuskatu 45	\N	Helsinki	\N	21240	Finland
187	Ashworth	Rachel	(171) 555-1555	Fauntleroy Circus	\N	Manchester	\N	EC2 5NT	UK
189	Cassidy	Dean	+353 1862 1555	25 Maiden Lane	Floor No. 4	Dublin	\N	2	Ireland
198	Taylor	Leslie	6175558428	16780 Pompton St.	\N	Brickhaven	MA	58339	USA
201	Devon	Elizabeth	(171) 555-2282	12, Berkeley Gardens Blvd	\N	Liverpool	\N	WX1 6LT	UK
202	Tamuri	Yoshi 	(604) 555-3392	1900 Oak St.	\N	Vancouver	BC	V3F 2K1	Canada
204	Barajas	Miguel	6175557555	7635 Spinnaker Dr.	\N	Brickhaven	MA	58339	USA
205	Young	Julie	6265557265	78934 Hillside Dr.	\N	Pasadena	CA	90003	USA
206	Walker	Brydey	+612 9411 1555	Suntec Tower Three	8 Temasek	Singapore	\N	038988	Singapore
209	Citeaux	Frédérique 	88.60.1555	24, place Kléber	\N	Strasbourg	\N	67000	France
211	Gao	Mike	+852 2251 1555	Bank of China Tower	1 Garden Road	Central Hong Kong	\N	\N	Hong Kong
216	Saavedra	Eduardo 	(93) 203 4555	Rambla de Cataluña, 23	\N	Barcelona	\N	08022	Spain
219	Young	Mary	3105552373	4097 Douglas Av.	\N	Glendale	CA	92561	USA
223	Kloss	Horst 	0372-555188	Taucherstraße 10	\N	Cunewalde	\N	01307	Germany
227	Ibsen	Palle	86 21 3555	Smagsloget 45	\N	Århus	\N	8200	Denmark
233	Fresnière	Jean 	(514) 555-8054	43 rue St. Laurent	\N	Montréal	Québec	H1J 1C3	Canada
237	Camino	Alejandra 	(91) 745 6555	Gran Vía, 1	\N	Madrid	\N	28001	Spain
239	Thompson	Valarie	7605558146	361 Furth Circle	\N	San Diego	CA	91217	USA
240	Bennett	Helen 	(198) 555-8888	Garden House	Crowther Way 23	Cowes	Isle of Wight	PO31 7PJ	UK
242	Roulet	Annette 	61.77.6555	1 rue Alsace-Lorraine	\N	Toulouse	\N	31000	France
247	Messner	Renate 	069-0555984	Magazinweg 7	\N	Frankfurt	\N	60528	Germany
249	Accorti	Paolo 	011-4988555	Via Monte Bianco 34	\N	Torino	\N	10100	Italy
250	Da Silva	Daniel	+33 1 46 62 7555	27 rue du Colonel Pierre Avia	\N	Paris	\N	75508	France
256	Tonini	Daniel 	30.59.8555	67, avenue de l'Europe	\N	Versailles	\N	78000	France
259	Pfalzheim	Henriette 	0221-5554327	Mehrheimerstr. 369	\N	Köln	\N	50739	Germany
260	Lincoln	Elizabeth 	(604) 555-4555	23 Tsawassen Blvd.	\N	Tsawassen	BC	T2F 8M4	Canada
273	Franken	Peter 	089-0877555	Berliner Platz 43	\N	München	\N	80805	Germany
276	O'Hara	Anna	02 9936 8555	201 Miller Street	Level 15	North Sydney	NSW	2060	Australia
278	Rovelli	Giovanni 	035-640555	Via Ludovico il Moro 22	\N	Bergamo	\N	24100	Italy
282	Huxley	Adrian	+61 2 9495 8555	Monitor Money Building	815 Pacific Hwy	Chatswood	NSW	2067	Australia
286	Hernandez	Marta	6175558555	39323 Spinnaker Dr.	\N	Cambridge	MA	51247	USA
293	Harrison	Ed	+41 26 425 50 01	Rte des Arsenaux 41 	\N	Fribourg	\N	1700	Switzerland
298	Holz	Mihael	0897-034555	Grenzacherweg 237	\N	Genève	\N	1203	Switzerland
299	Klaeboe	Jan	+47 2212 1555	Drammensveien 126A	PB 211 Sentrum	Oslo	\N	N 0106	Norway  
303	Schuyler	Bradley	+31 20 491 9555	Kingsfordweg 151	\N	Amsterdam	\N	1043 GR	Netherlands
307	Andersen	Mel	030-0074555	Obere Str. 57	\N	Berlin	\N	12209	Germany
311	Koskitalo	Pirkko	981-443655	Torikatu 38	\N	Oulu	\N	90110	Finland
314	Dewey	Catherine 	(02) 5554 67	Rue Joseph-Bens 532	\N	Bruxelles	\N	B-1180	Belgium
319	Frick	Steve	9145554562	3758 North Pendale Street	\N	White Plains	NY	24067	USA
320	Huang	Wing	5085559555	4575 Hillside Dr.	\N	New Bedford	MA	50553	USA
321	Brown	Julie	6505551386	7734 Strong St.	\N	San Francisco	CA	94217	USA
323	Graham	Mike	+64 9 312 5555	162-164 Grafton Road	Level 2	Auckland  	\N	\N	New Zealand
324	Brown	Ann 	(171) 555-0297	35 King George	\N	London	\N	WX3 6FW	UK
328	Brown	William	2015559350	7476 Moss Rd.	\N	Newark	NJ	94019	USA
333	Calaghan	Ben	61-7-3844-6555	31 Duncan St. West End	\N	South Brisbane	Queensland	4101	Australia
334	Suominen	Kalle	+358 9 8045 555	Software Engineering Center	SEC Oy	Espoo	\N	FIN-02271	Finland
335	Cramer	Philip 	0555-09555	Maubelstr. 90	\N	Brandenburg	\N	14776	Germany
339	Cervantes	Francisca	2155554695	782 First Street	\N	Philadelphia	PA	71270	USA
344	Fernandez	Jesus	+34 913 728 555	Merchants House	27-30 Merchant's Quay	Madrid	\N	28023	Spain
347	Chandler	Brian	2155554369	6047 Douglas Av.	\N	Los Angeles	CA	91003	USA
348	McKenna	Patricia 	2967 555	8 Johnstown Road	\N	Cork	Co. Cork	\N	Ireland
350	Lebihan	Laurence 	91.24.4555	12, rue des Bouchers	\N	Marseille	\N	13008	France
353	Henriot	Paul 	26.47.1555	59 rue de l'Abbaye	\N	Reims	\N	51100	France
356	Kuger	Armand	+27 21 550 3555	1250 Pretorius Street	\N	Hatfield	Pretoria	0028	South Africa
357	MacKinlay	Wales	64-9-3763555	199 Great North Road	\N	Auckland	\N	\N	New Zealand
361	Josephs	Karin	0251-555259	Luisenstr. 48	\N	Münster	\N	44087	Germany
362	Yoshido	Juri	6175559555	8616 Spinnaker Dr.	\N	Boston	MA	51003	USA
363	Young	Dorothy	6035558647	2304 Long Airport Avenue	\N	Nashua	NH	62005	USA
369	Rodriguez	Lino 	(1) 354-2555	Jardim das rosas n. 32	\N	Lisboa	\N	1675	Portugal
376	Urs	Braun	0452-076555	Hauptstr. 29	\N	Bern	\N	3012	Switzerland
379	Nelson	Allen	6175558555	7825 Douglas Av.	\N	Brickhaven	MA	58339	USA
381	Cartrain	Pascale 	(071) 23 67 2555	Boulevard Tirou, 255	\N	Charleroi	\N	B-6000	Belgium
382	Pipps	Georg 	6562-9555	Geislweg 14	\N	Salzburg	\N	5020	Austria
385	Cruz	Arnold	+63 2 555 3587	15 McCallum Street	NatWest Center #13-03	Makati City	\N	1227 MM	Philippines
386	Moroni	Maurizio 	0522-556555	Strada Provinciale 124	\N	Reggio Emilia	\N	42100	Italy
398	Shimamura	Akiko	+81 3 3584 0555	2-2-8 Roppongi	\N	Minato-ku	Tokyo	106-0032	Japan
406	Perrier	Dominique	(1) 47.55.6555	25, rue Lauriston	\N	Paris	\N	75016	France
409	Müller	Rita 	0711-555361	Adenauerallee 900	\N	Stuttgart	\N	70563	Germany
412	McRoy	Sarah	04 499 9555	101 Lambton Quay	Level 11	Wellington	\N	\N	New Zealand
415	Donnermeyer	Michael	 +49 89 61 08 9555	Hansastr. 15	\N	Munich	\N	80686	Germany
424	Hernandez	Maria	2125558493	5905 Pompton St.	Suite 750	NYC	NY	10022	USA
443	Feuer	Alexander 	0342-555176	Heerstr. 22	\N	Leipzig	\N	04179	Germany
447	Lewis	Dan	2035554407	2440 Pompton St.	\N	Glendale	CT	97561	USA
448	Larsson	Martha	0695-34 6555	Åkergatan 24	\N	Bräcke	\N	S-844 67	Sweden
450	Frick	Sue	4085553659	3086 Ingle Ln.	\N	San Jose	CA	94217	USA
452	Mendel	Roland 	7675-3555	Kirchgasse 6	\N	Graz	\N	8010	Austria
455	Murphy	Leslie	2035559545	567 North Pendale Street	\N	New Haven	CT	97823	USA
456	Choi	Yu	2125551957	5290 North Pendale Street	Suite 200	NYC	NY	10022	USA
458	Sommer	Martín 	(91) 555 22 82	C/ Araquil, 67	\N	Madrid	\N	28023	Spain
459	Ottlieb	Sven 	0241-039123	Walserweg 21	\N	Aachen	\N	52066	Germany
462	Benitez	Violeta	5085552555	1785 First Street	\N	New Bedford	MA	50553	USA
465	Anton	Carmen	+34 913 728555	c/ Gobelas, 19-1 Urb. La Florida	\N	Madrid	\N	28023	Spain
471	Clenahan	Sean	61-9-3844-6555	7 Allen Street	\N	Glen Waverly	Victoria	3150	Australia
473	Ricotti	Franco	+39 022515555	20093 Cologno Monzese	Alessandro Volta 16	Milan	\N	\N	Italy
475	Thompson	Steve	3105553722	3675 Furth Circle	\N	Burbank	CA	94019	USA
477	Moos	Hanna 	0621-08555	Forsterstr. 57	\N	Mannheim	\N	68306	Germany
480	Semenov	Alexander 	+7 812 293 0521	2 Pobedy Square	\N	Saint Petersburg	\N	196143	Russia
481	Altagar,G M	Raanan	+ 972 9 959 8555	3 Hagalim Blv.	\N	Herzlia	\N	47625	Israel
484	Roel	José Pedro 	(95) 555 82 82	C/ Romero, 33	\N	Sevilla	\N	41101	Spain
486	Salazar	Rosa	2155559857	11328 Douglas Av.	\N	Philadelphia	PA	71270	USA
487	Taylor	Sue	4155554312	2793 Furth Circle	\N	Brisbane	CA	94217	USA
489	Smith	Thomas 	(171) 555-7555	120 Hanover Sq.	\N	London	\N	WA1 1DP	UK
495	Franco	Valarie	6175552555	6251 Ingle Ln.	\N	Boston	MA	51003	USA
496	Snowden	Tony	+64 9 5555500	Arenales 1938 3'A'	\N	Auckland  	\N	\N	New Zealand
\.


--
-- TOC entry 3010 (class 0 OID 16414)
-- Dependencies: 202
-- Data for Name: cs_employees; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cs_employees (employeenumber, lastname, firstname, email) FROM stdin;
1	Lucas	Diego	lucas@classicmodelcars.com
2	Stockard	Fleta	stockard@classicmodelcars.com
3	Lindstedt	Margery	lindstedt@classicmodelcars.com
4	Nissen	Stacy	nissen@classicmodelcars.com
5	Gorecki	Camilla	gorecki@classicmodelcars.com
6	Schulze	Bernardina	schulze@classicmodelcars.com
7	Lamarre	Jan	lamarre@classicmodelcars.com
8	Flamm	Anissa	flamm@classicmodelcars.com
9	Whitehead	Palma	whitehead@classicmodelcars.com
10	Penhollow	Eric	penhollow@classicmodelcars.com
11	Matley	Josie	matley@classicmodelcars.com
12	Holliday	Carolyn	holliday@classicmodelcars.com
13	Grego	Fidela	grego@classicmodelcars.com
14	Starks	Wynona	starks@classicmodelcars.com
15	Roden	Chuck	roden@classicmodelcars.com
16	Caul	Glen	caul@classicmodelcars.com
17	Lyda	Hedwig	lyda@classicmodelcars.com
18	Minner	Angelique	minner@classicmodelcars.com
19	Barak	Mara	barak@classicmodelcars.com
20	Dall	Clarence	dall@classicmodelcars.com
21	Hilliker	Lorretta	hilliker@classicmodelcars.com
22	Rockefeller	Michaela	rockefeller@classicmodelcars.com
23	Habel	Claris	habel@classicmodelcars.com
24	Laforce	Kalyn	laforce@classicmodelcars.com
25	Throckmorton	Chante	throckmorton@classicmodelcars.com
26	Kornegay	Crystle	kornegay@classicmodelcars.com
27	Hassler	Karoline	hassler@classicmodelcars.com
28	Appell	Caron	appell@classicmodelcars.com
29	Wasinger	Sandra	wasinger@classicmodelcars.com
30	Gibbons	Keitha	gibbons@classicmodelcars.com
\.


--
-- TOC entry 3009 (class 0 OID 16404)
-- Dependencies: 201
-- Data for Name: cs_products; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cs_products (productcode, productname, productscale, productvendor, productdescription) FROM stdin;
S24_2011	18th century schooner	1:24	Carousel DieCast Legends	All wood with canvas sails. Many extras including rigging, long boats, pilot house, anchors, etc. Comes with 4 masts, all square-rigged.
S24_2022	1938 Cadillac V-16 Presidential Limousine	1:24	Classic Metal Creations	This 1:24 scale precision die cast replica of the 1938 Cadillac V-16 Presidential Limousine has all the details of the original, from the flags on the front to an opening back seat compartment complete with telephone and rifle. Features factory baked-enamel black finish, hood goddess ornament, working jump seats.
S24_2300	1962 Volkswagen Microbus	1:24	Autoart Studio Design	This 1:18 scale die cast replica of the 1962 Microbus is loaded with features: A working steering system, opening front doors and tailgate, and famous two-tone factory baked enamel finish, are all topped of by the sliding, real fabric, sunroof.
S24_2360	1982 Ducati 900 Monster	1:24	Highway 66 Mini Classics	Features two-tone paint with chrome accents, superior die-cast detail , rotating wheels , working kick stand
S24_2766	1949 Jaguar XK 120	1:24	Classic Metal Creations	Precision-engineered from original Jaguar specification in perfect scale ratio. Features opening doors, superb detail and craftsmanship, working steering system, opening forward compartment, opening rear trunk with removable spare, 4 wheel independent spring suspension as well as factory baked enamel finish.
S24_2840	1958 Chevy Corvette Limited Edition	1:24	Carousel DieCast Legends	The operating parts of this 1958 Chevy Corvette Limited Edition are particularly delicate due to their precise scale and require special care and attention. Features rotating wheels, working streering, opening doors and trunk. Color dark green.
S24_2841	1900s Vintage Bi-Plane	1:24	Autoart Studio Design	Hand crafted diecast-like metal bi-plane is re-created in about 1:24 scale of antique pioneer airplane. All hand-assembled with many different parts. Hand-painted in classic yellow and features correct markings of original airplane.
S24_2887	1952 Citroen-15CV	1:24	Exoto Designs	Precision crafted hand-assembled 1:18 scale reproduction of the 1952 15CV, with its independent spring suspension, working steering system, opening doors and hood, detailed engine and instrument panel, all topped of with a factory fresh baked enamel finish.
S24_2972	1982 Lamborghini Diablo	1:24	Second Gear Diecast	This replica features opening doors, superb detail and craftsmanship, working steering system, opening forward compartment, opening rear trunk with removable spare, 4 wheel independent spring suspension as well as factory baked enamel finish.
S24_3151	1912 Ford Model T Delivery Wagon	1:24	Min Lin Diecast	This model features chrome trim and grille, opening hood, opening doors, opening trunk, detailed engine, working steering system. Color white.
S24_3191	1969 Chevrolet Camaro Z28	1:24	Exoto Designs	1969 Z/28 Chevy Camaro 1:24 scale replica. The operating parts of this limited edition 1:24 scale diecast model car 1969 Chevy Camaro Z28- hood, trunk, wheels, streering, suspension and doors- are particularly delicate due to their precise scale and require special care and attention.
S24_3371	1971 Alpine Renault 1600s	1:24	Welly Diecast Productions	This 1971 Alpine Renault 1600s replica Features opening doors, superb detail and craftsmanship, working steering system, opening forward compartment, opening rear trunk with removable spare, 4 wheel independent spring suspension as well as factory baked enamel finish.
S24_3420	1937 Horch 930V Limousine	1:24	Autoart Studio Design	Features opening hood, opening doors, opening trunk, wide white wall tires, front door arm rests, working steering system
S10_1678	1969 Harley Davidson Ultimate Chopper	1:10	Min Lin Diecast	This replica features working kickstand, front suspension, gear-shift lever, footbrake lever, drive chain, wheels and steering. All parts are particularly delicate due to their precise scale and require special care and attention.
S10_1949	1952 Alpine Renault 1300	1:10	Classic Metal Creations	Turnable front wheels; steering function; detailed interior; detailed engine; opening hood; opening trunk; opening doors; and detailed chassis.
S10_2016	1996 Moto Guzzi 1100i	1:10	Highway 66 Mini Classics	Official Moto Guzzi logos and insignias, saddle bags located on side of motorcycle, detailed engine, working steering, working suspension, two leather seats, luggage rack, dual exhaust pipes, small saddle bag located on handle bars, two-tone paint with chrome accents, superior die-cast detail , rotating wheels , working kick stand, diecast metal with plastic parts and baked enamel finish.
S10_4698	2003 Harley-Davidson Eagle Drag Bike	1:10	Red Start Diecast	Model features, official Harley Davidson logos and insignias, detachable rear wheelie bar, heavy diecast metal with resin parts, authentic multi-color tampo-printed graphics, separate engine drive belts, free-turning front fork, rotating tires and rear racing slick, certificate of authenticity, detailed engine, display stand\n, precision diecast replica, baked enamel finish, 1:10 scale model, removable fender, seat and tank cover piece for displaying the superior detail of the v-twin engine
S10_4757	1972 Alfa Romeo GTA	1:10	Motor City Art Classics	Features include: Turnable front wheels; steering function; detailed interior; detailed engine; opening hood; opening trunk; opening doors; and detailed chassis.
S10_4962	1962 LanciaA Delta 16V	1:10	Second Gear Diecast	Features include: Turnable front wheels; steering function; detailed interior; detailed engine; opening hood; opening trunk; opening doors; and detailed chassis.
S12_1099	1968 Ford Mustang	1:12	Autoart Studio Design	Hood, doors and trunk all open to reveal highly detailed interior features. Steering wheel actually turns the front wheels. Color dark green.
S12_1108	2001 Ferrari Enzo	1:12	Second Gear Diecast	Turnable front wheels; steering function; detailed interior; detailed engine; opening hood; opening trunk; opening doors; and detailed chassis.
S12_1666	1958 Setra Bus	1:12	Welly Diecast Productions	Model features 30 windows, skylights & glare resistant glass, working steering system, original logos
S12_2823	2002 Suzuki XREO	1:12	Unimax Art Galleries	Official logos and insignias, saddle bags located on side of motorcycle, detailed engine, working steering, working suspension, two leather seats, luggage rack, dual exhaust pipes, small saddle bag located on handle bars, two-tone paint with chrome accents, superior die-cast detail , rotating wheels , working kick stand, diecast metal with plastic parts and baked enamel finish.
S12_3148	1969 Corvair Monza	1:18	Welly Diecast Productions	1:18 scale die-cast about 10" long doors open, hood opens, trunk opens and wheels roll
S12_3380	1968 Dodge Charger	1:12	Welly Diecast Productions	1:12 scale model of a 1968 Dodge Charger. Hood, doors and trunk all open to reveal highly detailed interior features. Steering wheel actually turns the front wheels. Color black
S700_3167	F/A 18 Hornet 1/72	1:72	Motor City Art Classics	10" Wingspan with retractable landing gears.Comes with pilot
S12_3891	1969 Ford Falcon	1:12	Second Gear Diecast	Turnable front wheels; steering function; detailed interior; detailed engine; opening hood; opening trunk; opening doors; and detailed chassis.
S12_3990	1970 Plymouth Hemi Cuda	1:12	Studio M Art Models	Very detailed 1970 Plymouth Cuda model in 1:12 scale. The Cuda is generally accepted as one of the fastest original muscle cars from the 1970s. This model is a reproduction of one of the orginal 652 cars built in 1970. Red color.
S12_4473	1957 Chevy Pickup	1:12	Exoto Designs	1:12 scale die-cast about 20" long Hood opens, Rubber wheels
S12_4675	1969 Dodge Charger	1:12	Welly Diecast Productions	Detailed model of the 1969 Dodge Charger. This model includes finely detailed interior and exterior features. Painted in red and white.
S18_1097	1940 Ford Pickup Truck	1:18	Studio M Art Models	This model features soft rubber tires, working steering, rubber mud guards, authentic Ford logos, detailed undercarriage, opening doors and hood,  removable split rear gate, full size spare mounted in bed, detailed interior with opening glove box
S18_1129	1993 Mazda RX-7	1:18	Highway 66 Mini Classics	This model features, opening hood, opening doors, detailed engine, rear spoiler, opening trunk, working steering, tinted windows, baked enamel finish. Color red.
S18_1342	1937 Lincoln Berline	1:18	Motor City Art Classics	Features opening engine cover, doors, trunk, and fuel filler cap. Color black
S18_1367	1936 Mercedes-Benz 500K Special Roadster	1:18	Studio M Art Models	This 1:18 scale replica is constructed of heavy die-cast metal and has all the features of the original: working doors and rumble seat, independent spring suspension, detailed interior, working steering system, and a bifold hood that reveals an engine so accurate that it even includes the wiring. All this is topped off with a baked enamel finish. Color white.
S18_1589	1965 Aston Martin DB5	1:18	Classic Metal Creations	Die-cast model of the silver 1965 Aston Martin DB5 in silver. This model includes full wire wheels and doors that open with fully detailed passenger compartment. In 1:18 scale, this model measures approximately 10 inches/20 cm long.
S18_1662	1980s Black Hawk Helicopter	1:18	Red Start Diecast	1:18 scale replica of actual Army's UH-60L BLACK HAWK Helicopter. 100% hand-assembled. Features rotating rotor blades, propeller blades and rubber wheels.
S18_1749	1917 Grand Touring Sedan	1:18	Welly Diecast Productions	This 1:18 scale replica of the 1917 Grand Touring car has all the features you would expect from museum quality reproductions: all four doors and bi-fold hood opening, detailed engine and instrument panel, chrome-look trim, and tufted upholstery, all topped off with a factory baked-enamel finish.
S18_1889	1948 Porsche 356-A Roadster	1:18	Gearbox Collectibles	This precision die-cast replica features opening doors, superb detail and craftsmanship, working steering system, opening forward compartment, opening rear trunk with removable spare, 4 wheel independent spring suspension as well as factory baked enamel finish.
S18_1984	1995 Honda Civic	1:18	Min Lin Diecast	This model features, opening hood, opening doors, detailed engine, rear spoiler, opening trunk, working steering, tinted windows, baked enamel finish. Color yellow.
S18_2238	1998 Chrysler Plymouth Prowler	1:18	Gearbox Collectibles	Turnable front wheels; steering function; detailed interior; detailed engine; opening hood; opening trunk; opening doors; and detailed chassis.
S18_2248	1911 Ford Town Car	1:18	Motor City Art Classics	Features opening hood, opening doors, opening trunk, wide white wall tires, front door arm rests, working steering system.
S18_2319	1964 Mercedes Tour Bus	1:18	Unimax Art Galleries	Exact replica. 100+ parts. working steering system, original logos
S18_2325	1932 Model A Ford J-Coupe	1:18	Autoart Studio Design	This model features grille-mounted chrome horn, lift-up louvered hood, fold-down rumble seat, working steering system, chrome-covered spare, opening doors, detailed and wired engine
S18_2432	1926 Ford Fire Engine	1:18	Carousel DieCast Legends	Gleaming red handsome appearance. Everything is here the fire hoses, ladder, axes, bells, lanterns, ready to fight any inferno.
S18_2581	P-51-D Mustang	1:72	Gearbox Collectibles	Has retractable wheels and comes with a stand
S18_2625	1936 Harley Davidson El Knucklehead	1:18	Welly Diecast Productions	Intricately detailed with chrome accents and trim, official die-struck logos and baked enamel finish.
S18_2795	1928 Mercedes-Benz SSK	1:18	Gearbox Collectibles	This 1:18 replica features grille-mounted chrome horn, lift-up louvered hood, fold-down rumble seat, working steering system, chrome-covered spare, opening doors, detailed and wired engine. Color black.
S18_2870	1999 Indy 500 Monte Carlo SS	1:18	Red Start Diecast	Features include opening and closing doors. Color: Red
S18_2949	1913 Ford Model T Speedster	1:18	Carousel DieCast Legends	This 250 part reproduction includes moving handbrakes, clutch, throttle and foot pedals, squeezable horn, detailed wired engine, removable water, gas, and oil cans, pivoting monocle windshield, all topped with a baked enamel red finish. Each replica comes with an Owners Title and Certificate of Authenticity. Color red.
S18_2957	1934 Ford V8 Coupe	1:18	Min Lin Diecast	Chrome Trim, Chrome Grille, Opening Hood, Opening Doors, Opening Trunk, Detailed Engine, Working Steering System
S18_3029	1999 Yamaha Speed Boat	1:18	Min Lin Diecast	Exact replica. Wood and Metal. Many extras including rigging, long boats, pilot house, anchors, etc. Comes with three masts, all square-rigged.
S18_3136	18th Century Vintage Horse Carriage	1:18	Red Start Diecast	Hand crafted diecast-like metal horse carriage is re-created in about 1:18 scale of antique horse carriage. This antique style metal Stagecoach is all hand-assembled with many different parts.\n\nThis collectible metal horse carriage is painted in classic Red, and features turning steering wheel and is entirely hand-finished.
S18_3140	1903 Ford Model A	1:18	Unimax Art Galleries	Features opening trunk,  working steering system
S18_3232	1992 Ferrari 360 Spider red	1:18	Unimax Art Galleries	his replica features opening doors, superb detail and craftsmanship, working steering system, opening forward compartment, opening rear trunk with removable spare, 4 wheel independent spring suspension as well as factory baked enamel finish.
S18_3233	1985 Toyota Supra	1:18	Highway 66 Mini Classics	This model features soft rubber tires, working steering, rubber mud guards, authentic Ford logos, detailed undercarriage, opening doors and hood, removable split rear gate, full size spare mounted in bed, detailed interior with opening glove box
S18_3259	Collectable Wooden Train	1:18	Carousel DieCast Legends	Hand crafted wooden toy train set is in about 1:18 scale, 25 inches in total length including 2 additional carts, of actual vintage train. This antique style wooden toy train model set is all hand-assembled with 100% wood.
S18_3278	1969 Dodge Super Bee	1:18	Min Lin Diecast	This replica features opening doors, superb detail and craftsmanship, working steering system, opening forward compartment, opening rear trunk with removable spare, 4 wheel independent spring suspension as well as factory baked enamel finish.
S18_3320	1917 Maxwell Touring Car	1:18	Exoto Designs	Features Gold Trim, Full Size Spare Tire, Chrome Trim, Chrome Grille, Opening Hood, Opening Doors, Opening Trunk, Detailed Engine, Working Steering System
S18_3482	1976 Ford Gran Torino	1:18	Gearbox Collectibles	Highly detailed 1976 Ford Gran Torino "Starsky and Hutch" diecast model. Very well constructed and painted in red and white patterns.
S18_3685	1948 Porsche Type 356 Roadster	1:18	Gearbox Collectibles	This model features working front and rear suspension on accurately replicated and actuating shock absorbers as well as opening engine cover, rear stabilizer flap,  and 4 opening doors.
S18_3782	1957 Vespa GS150	1:18	Studio M Art Models	Features rotating wheels , working kick stand. Comes with stand.
S18_3856	1941 Chevrolet Special Deluxe Cabriolet	1:18	Exoto Designs	Features opening hood, opening doors, opening trunk, wide white wall tires, front door arm rests, working steering system, leather upholstery. Color black.
S18_4027	1970 Triumph Spitfire	1:18	Min Lin Diecast	Features include opening and closing doors. Color: White.
S18_4409	1932 Alfa Romeo 8C2300 Spider Sport	1:18	Exoto Designs	This 1:18 scale precision die cast replica features the 6 front headlights of the original, plus a detailed version of the 142 horsepower straight 8 engine, dual spares and their famous comprehensive dashboard. Color black.
S18_4522	1904 Buick Runabout	1:18	Exoto Designs	Features opening trunk,  working steering system
S18_4600	1940s Ford truck	1:18	Motor City Art Classics	This 1940s Ford Pick-Up truck is re-created in 1:18 scale of original 1940s Ford truck. This antique style metal 1940s Ford Flatbed truck is all hand-assembled. This collectible 1940's Pick-Up truck is painted in classic dark green color, and features rotating wheels.
S18_4668	1939 Cadillac Limousine	1:18	Studio M Art Models	Features completely detailed interior including Velvet flocked drapes,deluxe wood grain floor, and a wood grain casket with seperate chrome handles
S18_4721	1957 Corvette Convertible	1:18	Classic Metal Creations	1957 die cast Corvette Convertible in Roman Red with white sides and whitewall tires. 1:18 scale quality die-cast with detailed engine and underbvody. Now you can own The Classic Corvette.
S18_4933	1957 Ford Thunderbird	1:18	Studio M Art Models	This 1:18 scale precision die-cast replica, with its optional porthole hardtop and factory baked-enamel Thunderbird Bronze finish, is a 100% accurate rendition of this American classic.
S24_1046	1970 Chevy Chevelle SS 454	1:24	Unimax Art Galleries	This model features rotating wheels, working streering system and opening doors. All parts are particularly delicate due to their precise scale and require special care and attention. It should not be picked up by the doors, roof, hood or trunk.
S24_1444	1970 Dodge Coronet	1:24	Highway 66 Mini Classics	1:24 scale die-cast about 18" long doors open, hood opens and rubber wheels
S24_1578	1997 BMW R 1100 S	1:24	Autoart Studio Design	Detailed scale replica with working suspension and constructed from over 70 parts
S24_1628	1966 Shelby Cobra 427 S/C	1:24	Carousel DieCast Legends	This diecast model of the 1966 Shelby Cobra 427 S/C includes many authentic details and operating parts. The 1:24 scale model of this iconic lighweight sports car from the 1960s comes in silver and it's own display case.
S24_1785	1928 British Royal Navy Airplane	1:24	Classic Metal Creations	Official logos and insignias
S24_1937	1939 Chevrolet Deluxe Coupe	1:24	Motor City Art Classics	This 1:24 scale die-cast replica of the 1939 Chevrolet Deluxe Coupe has the same classy look as the original. Features opening trunk, hood and doors and a showroom quality baked enamel finish.
S24_2000	1960 BSA Gold Star DBD34	1:24	Highway 66 Mini Classics	Detailed scale replica with working suspension and constructed from over 70 parts
S32_4485	1974 Ducati 350 Mk3 Desmo	1:32	Second Gear Diecast	This model features two-tone paint with chrome accents, superior die-cast detail , rotating wheels , working kick stand
S50_1341	1930 Buick Marquette Phaeton	1:50	Studio M Art Models	Features opening trunk,  working steering system
S50_1392	Diamond T620 Semi-Skirted Tanker	1:50	Highway 66 Mini Classics	This limited edition model is licensed and perfectly scaled for Lionel Trains. The Diamond T620 has been produced in solid precision diecast and painted with a fire baked enamel finish. It comes with a removable tanker and is a perfect model to add authenticity to your static train or car layout or to just have on display.
S50_1514	1962 City of Detroit Streetcar	1:50	Classic Metal Creations	This streetcar is a joy to see. It has 99 separate windows, electric wire guides, detailed interiors with seats, poles and drivers controls, rolling and turning wheel assemblies, plus authentic factory baked-enamel finishes (Green Hornet for Chicago and Cream and Crimson for Boston).
S50_4713	2002 Yamaha YZR M1	1:50	Autoart Studio Design	Features rotating wheels , working kick stand. Comes with stand.
S700_1138	The Schooner Bluenose	1:700	Autoart Studio Design	All wood with canvas sails. Measures 31 1/2 inches in Length, 22 inches High and 4 3/4 inches Wide. Many extras.\nThe schooner Bluenose was built in Nova Scotia in 1921 to fish the rough waters off the coast of Newfoundland. Because of the Bluenose racing prowess she became the pride of all Canadians. Still featured on stamps and the Canadian dime, the Bluenose was lost off Haiti in 1946.
S700_1691	American Airlines: B767-300	1:700	Min Lin Diecast	Exact replia with official logos and insignias and retractable wheels
S700_1938	The Mayflower	1:700	Studio M Art Models	Measures 31 1/2 inches Long x 25 1/2 inches High x 10 5/8 inches Wide\nAll wood with canvas sail. Extras include long boats, rigging, ladders, railing, anchors, side cannons, hand painted, etc.
S700_2047	HMS Bounty	1:700	Unimax Art Galleries	Measures 30 inches Long x 27 1/2 inches High x 4 3/4 inches Wide. \nMany extras including rigging, long boats, pilot house, anchors, etc. Comes with three masts, all square-rigged.
S700_2466	America West Airlines B757-200	1:700	Motor City Art Classics	Official logos and insignias. Working steering system. Rotating jet engines
S700_2610	The USS Constitution Ship	1:700	Red Start Diecast	All wood with canvas sails. Measures 31 1/2" Length x 22 3/8" High x 8 1/4" Width. Extras include 4 boats on deck, sea sprite on bow, anchors, copper railing, pilot houses, etc.
S700_2824	1982 Camaro Z28	1:18	Carousel DieCast Legends	Features include opening and closing doors. Color: White. \nMeasures approximately 9 1/2" Long.
S700_2834	ATA: B757-300	1:700	Highway 66 Mini Classics	Exact replia with official logos and insignias and retractable wheels
S700_3505	The Titanic	1:700	Carousel DieCast Legends	Completed model measures 19 1/2 inches long, 9 inches high, 3inches wide and is in barn red/black. All wood and metal.
S700_3962	The Queen Mary	1:700	Welly Diecast Productions	Exact replica. Wood and Metal. Many extras including rigging, long boats, pilot house, anchors, etc. Comes with three masts, all square-rigged.
S700_4002	American Airlines: MD-11S	1:700	Second Gear Diecast	Polished finish. Exact replia with official logos and insignias and retractable wheels
S72_1253	Boeing X-32A JSF	1:72	Motor City Art Classics	10" Wingspan with retractable landing gears.Comes with pilot
S72_3212	Pont Yacht	1:72	Unimax Art Galleries	Measures 38 inches Long x 33 3/4 inches High. Includes a stand.\nMany extras including rigging, long boats, pilot house, anchors, etc. Comes with 2 masts, all square-rigged
S24_3432	2002 Chevy Corvette	1:24	Gearbox Collectibles	The operating parts of this limited edition Diecast 2002 Chevy Corvette 50th Anniversary Pace car Limited Edition are particularly delicate due to their precise scale and require special care and attention. Features rotating wheels, poseable streering, opening doors and trunk.
S24_3816	1940 Ford Delivery Sedan	1:24	Carousel DieCast Legends	Chrome Trim, Chrome Grille, Opening Hood, Opening Doors, Opening Trunk, Detailed Engine, Working Steering System. Color black.
S24_3856	1956 Porsche 356A Coupe	1:18	Classic Metal Creations	Features include: Turnable front wheels; steering function; detailed interior; detailed engine; opening hood; opening trunk; opening doors; and detailed chassis.
S24_3949	Corsair F4U ( Bird Cage)	1:24	Second Gear Diecast	Has retractable wheels and comes with a stand. Official logos and insignias.
S24_3969	1936 Mercedes Benz 500k Roadster	1:24	Red Start Diecast	This model features grille-mounted chrome horn, lift-up louvered hood, fold-down rumble seat, working steering system and rubber wheels. Color black.
S24_4048	1992 Porsche Cayenne Turbo Silver	1:24	Exoto Designs	This replica features opening doors, superb detail and craftsmanship, working steering system, opening forward compartment, opening rear trunk with removable spare, 4 wheel independent spring suspension as well as factory baked enamel finish.
S24_4258	1936 Chrysler Airflow	1:24	Second Gear Diecast	Features opening trunk,  working steering system. Color dark green.
S24_4278	1900s Vintage Tri-Plane	1:24	Unimax Art Galleries	Hand crafted diecast-like metal Triplane is Re-created in about 1:24 scale of antique pioneer airplane. This antique style metal triplane is all hand-assembled with many different parts.
S24_4620	1961 Chevrolet Impala	1:18	Classic Metal Creations	This 1:18 scale precision die-cast reproduction of the 1961 Chevrolet Impala has all the features-doors, hood and trunk that open; detailed 409 cubic-inch engine; chrome dashboard and stick shift, two-tone interior; working steering system; all topped of with a factory baked-enamel finish.
S32_1268	1980’s GM Manhattan Express	1:32	Motor City Art Classics	This 1980’s era new look Manhattan express is still active, running from the Bronx to mid-town Manhattan. Has 35 opeining windows and working lights. Needs a battery.
S32_1374	1997 BMW F650 ST	1:32	Exoto Designs	Features official die-struck logos and baked enamel finish. Comes with stand.
S32_2206	1982 Ducati 996 R	1:32	Gearbox Collectibles	Features rotating wheels , working kick stand. Comes with stand.
S32_2509	1954 Greyhound Scenicruiser	1:32	Classic Metal Creations	Model features bi-level seating, 50 windows, skylights & glare resistant glass, working steering system, original logos
S32_3207	1950's Chicago Surface Lines Streetcar	1:32	Gearbox Collectibles	This streetcar is a joy to see. It has 80 separate windows, electric wire guides, detailed interiors with seats, poles and drivers controls, rolling and turning wheel assemblies, plus authentic factory baked-enamel finishes (Green Hornet for Chicago and Cream and Crimson for Boston).
S32_3522	1996 Peterbilt 379 Stake Bed with Outrigger	1:32	Red Start Diecast	This model features, opening doors, detailed engine, working steering, tinted windows, detailed interior, die-struck logos, removable stakes operating outriggers, detachable second trailer, functioning 360-degree self loader, precision molded resin trailer and trim, baked enamel finish on cab
S32_4289	1928 Ford Phaeton Deluxe	1:32	Highway 66 Mini Classics	This model features grille-mounted chrome horn, lift-up louvered hood, fold-down rumble seat, working steering system
\.


--
-- TOC entry 2872 (class 2606 OID 16423)
-- Name: cs_customer_products cs_customer_products_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_customer_products
    ADD CONSTRAINT cs_customer_products_pk PRIMARY KEY (customernumber, productcode);


--
-- TOC entry 2866 (class 2606 OID 16402)
-- Name: cs_customers cs_customers_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_customers
    ADD CONSTRAINT cs_customers_pk PRIMARY KEY (customernumber);


--
-- TOC entry 2870 (class 2606 OID 16418)
-- Name: cs_employees cs_employees_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_employees
    ADD CONSTRAINT cs_employees_pk PRIMARY KEY (employeenumber);


--
-- TOC entry 2868 (class 2606 OID 16411)
-- Name: cs_products cs_products_pk; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_products
    ADD CONSTRAINT cs_products_pk PRIMARY KEY (productcode);


--
-- TOC entry 2876 (class 2606 OID 16442)
-- Name: cs_customer_calls cs_customer_calls_fk1; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_customer_calls
    ADD CONSTRAINT cs_customer_calls_fk1 FOREIGN KEY (customernumber) REFERENCES public.cs_customers(customernumber);


--
-- TOC entry 2875 (class 2606 OID 16437)
-- Name: cs_customer_calls cs_customer_calls_fk2; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_customer_calls
    ADD CONSTRAINT cs_customer_calls_fk2 FOREIGN KEY (employeenumber) REFERENCES public.cs_employees(employeenumber);


--
-- TOC entry 2877 (class 2606 OID 16447)
-- Name: cs_customer_calls cs_customer_calls_fk3; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_customer_calls
    ADD CONSTRAINT cs_customer_calls_fk3 FOREIGN KEY (productcode) REFERENCES public.cs_products(productcode);


--
-- TOC entry 2873 (class 2606 OID 16424)
-- Name: cs_customer_products cs_customer_products_fk1; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_customer_products
    ADD CONSTRAINT cs_customer_products_fk1 FOREIGN KEY (customernumber) REFERENCES public.cs_customers(customernumber);


--
-- TOC entry 2874 (class 2606 OID 16429)
-- Name: cs_customer_products cs_customer_products_fk2; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cs_customer_products
    ADD CONSTRAINT cs_customer_products_fk2 FOREIGN KEY (productcode) REFERENCES public.cs_products(productcode);


-- Completed on 2021-02-09 20:48:26

--
-- PostgreSQL database dump complete
--

