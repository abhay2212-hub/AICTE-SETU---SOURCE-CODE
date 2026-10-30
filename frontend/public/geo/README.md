<!-- Owner: Dev B -->
# India state and UT boundaries

`india-states.topo.json` is the state map used by `/map` (F27).

## Source

- Dataset: DataMeet India Community Maps Project, **States layer** (`States/Admin2.shp`)
  https://github.com/datameet/maps/tree/master/States
- Version: commit `2c0c306a0c786a83876065a62b7b82646d8a639d` (2021-10-25, "Merged the two Ladhak
  features"), after "Updated Ladhak & J&K boundry as per latest SOI Map" (2021-08-24) and
  "Updated the States & UT to status as per Jan 2020" (2020-05-06).
- 36 features: 28 states and 8 union territories, with Jammu & Kashmir and Ladakh as two
  separate UTs and Dadra and Nagar Haveli and Daman and Diu merged (status as of 2020).

## Licence and attribution

The DataMeet repository states: "Unless explicitly stated, all datasets in this repository is
shared under CC BY 4.0". (The older DataMeet documentation page for the States layer lists
CC BY 2.5 India; both licences only require attribution.)

Attribution, shown on the map page:

> India state boundaries: [DataMeet India Community Maps Project](https://github.com/datameet/maps)
> ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)). Simplified.

## How the file was made

Downloaded `Admin2.shp/.shx/.dbf/.prj/.cpg` to a temporary folder outside the repo, then:

```sh
npx mapshaper@0.6.102 Admin2.shp -rename-fields name=ST_NM -simplify dp 3% keep-shapes -clean -rename-layers states -o india-states.topo.json format=topojson quantization=100000
```

Coordinates are WGS84 longitude/latitude. Object name: `states`. One property per feature: `name`
(the source's `ST_NM`).

## Boundary checks (official depiction, Survey of India)

- The outer outline was compared with the **Survey of India India boundary** published in the same
  repository (`Survey-of-India-Index-Maps/IndiaBoundary`, "A Survey of India download",
  indiamaps.gov.in). Union of all 36 features: 3,285,009 km²; Survey of India outline:
  3,291,274 km² (official area of India: 3,287,263 km²). The only differences of 200 km² or more
  are coastal (Gulf of Khambhat and the Kutch coast, about 3,200 km² of mostly water in the
  Survey of India polygon). **No difference in Jammu and Kashmir, Ladakh or Arunachal Pradesh.**
- Jammu & Kashmir (73.39–76.78 °E, up to 35.12 °N) includes the areas west of the Line of Control.
  Ladakh (72.53–80.33 °E, up to 37.08 °N) includes Gilgit-Baltistan and Aksai Chin. Northern tip of
  the union: 37.08 °N, as in the Survey of India outline (37.09 °N).
- Arunachal Pradesh is complete; Andaman & Nicobar (96 island parts after simplification) and
  Lakshadweep (9 parts) are present.

## Names

Feature names match the platform's `institutions.state` values exactly for every state the
platform uses (fixtures, `datagen/generate.py` and the demo database). The two UT names that use
"&" are "Jammu & Kashmir" and "Andaman & Nicobar". `frontend/src/pages/map/states.ts` holds the
name map, including aliases such as "NCT of Delhi" and "Orissa".
