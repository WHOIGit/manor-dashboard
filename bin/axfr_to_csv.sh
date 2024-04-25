#!/bin/bash

# A script to map CNAME records to a parent host record in DNS.  This is only doable by parsing
#   DNS zone transfers.  DNS zone transfers are an authenticated action, so we can only do this
#   on a system that is able to use the 'axfr-whoi' script which handles the authentication.

# Output is a CSV file with these headings:
#   1.  Host IP
#   2.  Host FQDN
#   3.  A space-delimited string containing all DNS CNAME records associated with the FQDN

# 2022-04-20 Kodiak Firesmith <kfiresmith@whoi.edu>


debug=false
tmpdir=/tmp/map-cnames

[ -d "$tmpdir" ] || mkdir -p $tmpdir

# Prepare by pulling a single zone transfer to work with
./axfr-whoi > $tmpdir/zone.out

if [ ! -z $1 ]; then
  vlanid=$1
else
  read -p "Enter a VLAN number from this list to map: 76, 129, 181, 208, 216, 235, 1048, 1049, 1050, ooinet, all    " vlanid
fi

case $vlanid in
  76)
  netrange='128.128.76|128.128.77|128.128.78|128.128.79'
  ;;
  129)
  netrange='128.128.129'
  ;;
  181)
  netrange='128.128.181'
  ;;
  208)
  netrange='128.128.208'
  ;;
  216)
  netrange='128.128.216'
  ;;
  235)
  netrange='128.128.235'
  ;;
  1048)
  netrange='10.128.48'
  ;;
  1049)
  netrange='10.128.49'
  ;;
  1050)
  netrange='10.128.50'
  ;;
  ooinet)
  netrange='199.92.168'
  ;;
  all)
  netrange='128.128.76.|128.128.77.|128.128.78.|128.128.79.|128.128.129.|128.128.181.|128.128.208.|128.128.216.|128.128.235.|10.128.48.|10.128.49.|10.128.50.|199.92.168.'
  ;;
  *)
  echo "You must use a valid vlan ID from this list to map: 76, 129, 181, 208, 216, 235, 1048, 1049, 1050, ooinet, all"
  exit 1
esac

csvfile=$vlanid-output.csv
# Flush contents of csv before we populate it
echo "Host IP, Host FQDN, CNAMEs"> $tmpdir/$csvfile

egrep $netrange $tmpdir/zone.out | awk '{print $5, $1}' | sort -V | sed 's/.$//g' > $tmpdir/$vlanid-records

while read -r line;
do
  # Set the HOST IP and FQDN variables for each host record
  hostip="$(echo $line | awk '{print $1}')"
  hostrecord="$(echo $line | awk '{print $2}')"
  # Count the number of associated CNAME records for each host record
  cnamecount="$(egrep "$hostrecord" $tmpdir/zone.out | grep CNAME | awk '{print $1}' | sed 's/.$//g' | wc -l)"
  # Only bother to create entries in CSV file if the host has CNAME records associated with it
  if [ "$cnamecount" -gt "0" ]; then
    # Debugging - count CNAME records for each FQDN
    if $debug; then
      echo "$hostrecord has $cnamecount CNAME records"
    fi
    # This is a hack to prevent whoi.edu from returning everything as a cname record
    if [ "$hostrecord" == "whoi.edu" ]; then
      cnamerecords="www.whoi.edu www.whoi.net"
    else
      # Here we assemble a space-delimited sorted list of associated CNAMEs as a single string
      cnamerecords="$(egrep "$hostrecord" $tmpdir/zone.out | grep CNAME | awk '{print $1}' | sed 's/.$//g' | sort | paste -s -d ' ')"
    fi
    # Here we add the map entry for host IP, FQDN, and CNAMEs
    echo "$hostip,$hostrecord,$cnamerecords" | tee -a $tmpdir/$csvfile
    # Remove any blank lines from output CSV
    sed -i '/^[[:space:]]*$/d' $tmpdir/$csvfile
  fi
done < $tmpdir/$vlanid-records

# Clean up the intermediate records file
rm $tmpdir/$vlanid-records
