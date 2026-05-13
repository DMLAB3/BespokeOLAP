building.parquet
  b_buildingkey: int64 not null
  b_name: string not null
  b_boundary: binary not null
  rows: 0

customer.parquet
  c_custkey: int64 not null
  c_name: string not null
  c_address: string not null
  c_region: string not null
  c_nation: string not null
  c_phone: string not null
  rows: 3000

driver.parquet
  d_driverkey: int64 not null
  d_name: string not null
  d_address: string not null
  d_region: string not null
  d_nation: string not null
  d_phone: string not null
  rows: 50

trip.parquet
  t_tripkey: int64 not null
  t_custkey: int64 not null
  t_driverkey: int64 not null
  t_vehiclekey: int64 not null
  t_pickuptime: timestamp[ms] not null
  t_dropofftime: timestamp[ms] not null
  t_fare: decimal128(15, 5) not null
  t_tip: decimal128(15, 5) not null
  t_totalamount: decimal128(15, 5) not null
  t_distance: decimal128(15, 5) not null
  t_pickuploc: binary not null
  t_dropoffloc: binary not null
  rows: 600000

vehicle.parquet
  v_vehiclekey: int64 not null
  v_mfgr: string not null
  v_brand: string not null
  v_type: string not null
  v_comment: string not null
  rows: 10

zone.parquet
  z_zonekey: int64 not null
  z_gersid: string not null
  z_country: string not null
  z_region: string not null
  z_name: string not null
  z_subtype: string not null
  z_boundary: binary
  rows: 156095
