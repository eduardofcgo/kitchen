create table if not exists invoice(
  id int primary key,
  delivery_code string unique,
  talao blob not null,
  print_id string
);
