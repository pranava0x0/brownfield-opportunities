// Project planning assumptions and tri-state land filters. No suitability totals.
const REACTOR_CLASSES = Object.freeze({
  ap1000: Object.freeze({
    label: "AP1000", group: "Large PWR", mwe: 1117,
    consumptive_cfs: 31.1, withdrawal_cfs: 41.5,
    min_acres: 500, volt_profile: "large", dry_cooling_viable: false,
    spec_source: "https://westinghousenuclear.com/new-plants/ap1000-pwr/overview/",
    water_source: "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf",
    water_basis: "Vogtle 3&4 FEIS as-built record: 26.8 MGD withdrawal / 20.1 MGD (31.1 cfs) consumptive per unit, natural-draft towers",
  }),
  apr1400: Object.freeze({
    label: "APR1400", group: "Large PWR", mwe: 1400,
    consumptive_cfs: 39.0, withdrawal_cfs: 52.0,
    min_acres: 500, volt_profile: "large", dry_cooling_viable: false,
    spec_source: "https://www.nrc.gov/reactors/new-reactors/large-lwr/design-cert/apr1400.html",
    water_source: "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf",
    water_basis: "Linear per-MWe scaling of the Vogtle 3&4 record (31.1 cfs × 1400/1117) — no US APR1400 EIS exists; comparable thermal efficiency",
  }),
  ap300: Object.freeze({
    label: "AP300-class SMR", group: "SMR", mwe: 330,
    consumptive_cfs: 9.2, withdrawal_cfs: 12.3,
    min_acres: 100, volt_profile: "smr", dry_cooling_viable: null,
    spec_source: "https://westinghousenuclear.com/new-plants/ap300-smr/",
    water_source: "https://www.energy.gov/sites/default/files/EIS-0476-FEIS_Part1-2012.pdf",
    water_basis: "Screening estimate: linear per-MWe scaling of the Vogtle 3&4 wet-cooling record (31.1 cfs × 330/1117); no design-specific US operating water record is available",
  }),
  micro: Object.freeze({
    label: "Microreactor (Janus program)", group: "Microreactor", mwe: null,
    consumptive_cfs: null, withdrawal_cfs: null,
    min_acres: 20, volt_profile: "micro", dry_cooling_viable: null,
    spec_source: "https://www.army.mil/article/289074/army_announces_next_steps_on_janus_program_for_next_generation_nuclear_energy",
    water_source: "https://www.army.mil/article/289074/army_announces_next_steps_on_janus_program_for_next_generation_nuclear_energy",
    water_basis: "Unassessed: the Army is soliciting commercial concepts and has not paired reactor designs with installations; cooling technology and water demand remain vendor-specific",
  }),
});
const MICRO_MIN_ACRES = 5;
const NICKEL_MIN_ACRES = 300;
const NICKEL_MIN_ACRES_RECYCLING = 100;
const finiteArea = n => typeof n === "number" && Number.isFinite(n) && n >= 0;
function nickelAcreageStatus(site, minAcres = NICKEL_MIN_ACRES) {
  const ac = site?.acreage ?? site?.parcel_acreage;
  return finiteArea(ac) ? ac >= minAcres : null;
}
function microreactorMeetsAcreageThreshold(site) { return nickelAcreageStatus(site, MICRO_MIN_ACRES); }
function microreactorGridAccessMi(site) {
  const distances = [site?.transmission_mi, site?.substation_mi].filter(finiteArea);
  return distances.length ? Math.min(...distances) : null;
}
function ap1000MeetsAcreageThreshold(site, classKey) {
  const acres = site?.developable_acreage;
  return finiteArea(acres) ? acres >= (REACTOR_CLASSES[classKey] || REACTOR_CLASSES.ap1000).min_acres : null;
}
window.REACTOR_CLASSES = REACTOR_CLASSES;
window.ap1000MeetsAcreageThreshold = ap1000MeetsAcreageThreshold;
